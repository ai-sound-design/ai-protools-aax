#!/usr/bin/env python3
"""
Audio Precision Comparison Tool

Compares two audio files (generated with/without full_precision) using:
1. ffprobe - Technical metadata (bitrate, format, etc.)
2. Spectral analysis - Frequency content differences
3. Statistical analysis - Waveform differences

Usage:
    python compare_audio_precision.py audio_bf16.flac audio_fp32.flac
"""

import sys
import json
import subprocess
import numpy as np
import torch
import torchaudio
import matplotlib.pyplot as plt
from pathlib import Path
from typing import Dict, Tuple

def run_ffprobe(audio_path: Path) -> Dict:
    """Run ffprobe and return JSON output"""
    cmd = [
        'ffprobe',
        '-v', 'quiet',
        '-print_format', 'json',
        '-show_format',
        '-show_streams',
        str(audio_path)
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    return json.loads(result.stdout)

def analyze_waveform(audio_path: Path) -> Dict:
    """Analyze audio waveform statistics"""
    waveform, sample_rate = torchaudio.load(audio_path)
    waveform_np = waveform.numpy()[0]  # First channel
    
    return {
        "sample_rate": sample_rate,
        "duration_sec": waveform.shape[1] / sample_rate,
        "num_samples": waveform.shape[1],
        "num_channels": waveform.shape[0],
        "peak_amplitude": float(np.max(np.abs(waveform_np))),
        "rms_amplitude": float(np.sqrt(np.mean(waveform_np**2))),
        "dynamic_range_db": float(20 * np.log10(np.max(np.abs(waveform_np)) / (np.std(waveform_np) + 1e-10))),
        "mean": float(np.mean(waveform_np)),
        "std": float(np.std(waveform_np)),
        "min": float(np.min(waveform_np)),
        "max": float(np.max(waveform_np))
    }

def compute_spectral_difference(audio1: Path, audio2: Path) -> Dict:
    """Compute spectral differences between two audio files"""
    waveform1, sr1 = torchaudio.load(audio1)
    waveform2, sr2 = torchaudio.load(audio2)
    
    if sr1 != sr2:
        raise ValueError(f"Sample rates don't match: {sr1} vs {sr2}")
    
    # Compute spectrograms (STFT)
    spectrogram_transform = torchaudio.transforms.Spectrogram(
        n_fft=2048,
        hop_length=512,
        power=2.0
    )
    
    spec1 = spectrogram_transform(waveform1)[0].numpy()  # First channel
    spec2 = spectrogram_transform(waveform2)[0].numpy()
    
    # Compute differences
    spec_diff = np.abs(spec1 - spec2)
    spec_diff_db = 20 * np.log10(spec_diff + 1e-10)
    
    # Statistical measures
    correlation = np.corrcoef(spec1.flatten(), spec2.flatten())[0, 1]
    
    # Frequency band analysis (split spectrum into bands)
    num_bands = 10
    band_size = spec1.shape[0] // num_bands
    band_diffs = []
    
    for i in range(num_bands):
        start = i * band_size
        end = (i + 1) * band_size
        band1 = spec1[start:end, :]
        band2 = spec2[start:end, :]
        band_diff = np.mean(np.abs(band1 - band2))
        band_diffs.append(float(band_diff))
    
    return {
        "spectral_correlation": float(correlation),
        "mean_spectral_difference": float(np.mean(spec_diff)),
        "max_spectral_difference": float(np.max(spec_diff)),
        "mean_spectral_difference_db": float(np.mean(spec_diff_db)),
        "frequency_band_differences": band_diffs,
        "spectral_similarity_percent": float(correlation * 100)
    }

def compute_waveform_difference(audio1: Path, audio2: Path) -> Dict:
    """Compute direct waveform differences"""
    waveform1, sr1 = torchaudio.load(audio1)
    waveform2, sr2 = torchaudio.load(audio2)
    
    if sr1 != sr2:
        raise ValueError(f"Sample rates don't match: {sr1} vs {sr2}")
    
    # Convert to numpy
    wave1 = waveform1.numpy()[0]
    wave2 = waveform2.numpy()[0]
    
    # Ensure same length (trim to shorter)
    min_len = min(len(wave1), len(wave2))
    wave1 = wave1[:min_len]
    wave2 = wave2[:min_len]
    
    # Compute differences
    diff = wave1 - wave2
    abs_diff = np.abs(diff)
    
    # Signal-to-Noise Ratio (SNR)
    signal_power = np.mean(wave1**2)
    noise_power = np.mean(diff**2)
    snr_db = 10 * np.log10(signal_power / (noise_power + 1e-10))
    
    # Peak Signal-to-Noise Ratio (PSNR)
    max_val = max(np.max(np.abs(wave1)), np.max(np.abs(wave2)))
    mse = np.mean(diff**2)
    psnr_db = 20 * np.log10(max_val / np.sqrt(mse + 1e-10))
    
    # Correlation
    correlation = np.corrcoef(wave1, wave2)[0, 1]
    
    return {
        "mean_absolute_difference": float(np.mean(abs_diff)),
        "max_absolute_difference": float(np.max(abs_diff)),
        "rms_difference": float(np.sqrt(np.mean(diff**2))),
        "snr_db": float(snr_db),
        "psnr_db": float(psnr_db),
        "waveform_correlation": float(correlation),
        "waveform_similarity_percent": float(correlation * 100),
        "samples_identical": int(np.sum(diff == 0)),
        "samples_total": len(diff),
        "percent_identical": float(np.sum(diff == 0) / len(diff) * 100)
    }

def generate_comparison_plot(audio1: Path, audio2: Path, output_path: Path):
    """Generate visual comparison plots"""
    waveform1, sr = torchaudio.load(audio1)
    waveform2, _ = torchaudio.load(audio2)
    
    wave1 = waveform1.numpy()[0]
    wave2 = waveform2.numpy()[0]
    
    # Trim to same length
    min_len = min(len(wave1), len(wave2))
    wave1 = wave1[:min_len]
    wave2 = wave2[:min_len]
    
    # Time axis
    time = np.arange(len(wave1)) / sr
    
    # Create subplots
    fig, axes = plt.subplots(4, 1, figsize=(15, 12))
    
    # Plot 1: Waveforms overlay (first 2 seconds)
    sample_end = min(int(2 * sr), len(wave1))
    axes[0].plot(time[:sample_end], wave1[:sample_end], label='bfloat16', alpha=0.7)
    axes[0].plot(time[:sample_end], wave2[:sample_end], label='float32', alpha=0.7)
    axes[0].set_xlabel('Time (s)')
    axes[0].set_ylabel('Amplitude')
    axes[0].set_title('Waveform Comparison (First 2 seconds)')
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)
    
    # Plot 2: Difference signal
    diff = wave1 - wave2
    axes[1].plot(time[:sample_end], diff[:sample_end], color='red')
    axes[1].set_xlabel('Time (s)')
    axes[1].set_ylabel('Difference')
    axes[1].set_title('Waveform Difference (bfloat16 - float32)')
    axes[1].grid(True, alpha=0.3)
    
    # Plot 3 & 4: Spectrograms using scipy
    # Fixed: Use proper spectrogram instead of manual FFT reshape
    from scipy import signal
    
    n_fft = 2048
    hop_length = 512
    
    # Compute spectrograms using scipy's spectrogram
    f1, t1, spec1 = signal.spectrogram(wave1, fs=sr, nperseg=n_fft, noverlap=n_fft-hop_length)
    f2, t2, spec2 = signal.spectrogram(wave2, fs=sr, nperseg=n_fft, noverlap=n_fft-hop_length)
    
    # Convert to dB scale
    spec1_db = 10 * np.log10(spec1 + 1e-10)
    spec2_db = 10 * np.log10(spec2 + 1e-10)
    
    # Plot only first 5 seconds and up to 10kHz for clarity
    time_limit = min(5.0, t1[-1])
    freq_limit = 10000  # Hz
    time_idx = np.where(t1 <= time_limit)[0]
    freq_idx = np.where(f1 <= freq_limit)[0]
    
    im1 = axes[2].imshow(spec1_db[np.ix_(freq_idx, time_idx)], 
                         aspect='auto', origin='lower', cmap='viridis',
                         extent=[0, time_limit, 0, freq_limit/1000])
    axes[2].set_title('Spectrogram: bfloat16')
    axes[2].set_ylabel('Frequency (kHz)')
    axes[2].set_xlabel('Time (s)')
    plt.colorbar(im1, ax=axes[2], label='Power (dB)')
    
    im2 = axes[3].imshow(spec2_db[np.ix_(freq_idx, time_idx)], 
                         aspect='auto', origin='lower', cmap='viridis',
                         extent=[0, time_limit, 0, freq_limit/1000])
    axes[3].set_title('Spectrogram: float32')
    axes[3].set_ylabel('Frequency (kHz)')
    axes[3].set_xlabel('Time (s)')
    plt.colorbar(im2, ax=axes[3], label='Power (dB)')
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"📊 Comparison plot saved to: {output_path}")

def main():
    if len(sys.argv) != 3:
        print("Usage: python compare_audio_precision.py <audio_bf16.flac> <audio_fp32.flac>")
        sys.exit(1)
    
    audio1 = Path(sys.argv[1])
    audio2 = Path(sys.argv[2])
    
    if not audio1.exists() or not audio2.exists():
        print(f"Error: One or both files don't exist")
        sys.exit(1)
    
    print("=" * 80)
    print("AUDIO PRECISION COMPARISON ANALYSIS")
    print("=" * 80)
    print(f"File 1 (bfloat16): {audio1.name}")
    print(f"File 2 (float32):  {audio2.name}")
    print("=" * 80)
    print()
    
    # 1. ffprobe metadata
    print("1. TECHNICAL METADATA (ffprobe)")
    print("-" * 80)
    
    probe1 = run_ffprobe(audio1)
    probe2 = run_ffprobe(audio2)
    
    format1 = probe1['format']
    format2 = probe2['format']
    
    print(f"Format:      {format1['format_name']:20} vs {format2['format_name']}")
    print(f"Duration:    {float(format1['duration']):20.3f} vs {float(format2['duration']):.3f} sec")
    print(f"Bit rate:    {int(format1['bit_rate']):20} vs {int(format2['bit_rate'])} bps")
    print(f"Size:        {int(format1['size']):20} vs {int(format2['size'])} bytes")
    print()
    
    # 2. Waveform statistics
    print("2. WAVEFORM STATISTICS")
    print("-" * 80)
    
    stats1 = analyze_waveform(audio1)
    stats2 = analyze_waveform(audio2)
    
    print(f"Peak Amplitude:    {stats1['peak_amplitude']:20.6f} vs {stats2['peak_amplitude']:.6f}")
    print(f"RMS Amplitude:     {stats1['rms_amplitude']:20.6f} vs {stats2['rms_amplitude']:.6f}")
    print(f"Dynamic Range:     {stats1['dynamic_range_db']:20.2f} vs {stats2['dynamic_range_db']:.2f} dB")
    print(f"Mean:              {stats1['mean']:20.6f} vs {stats2['mean']:.6f}")
    print(f"Std Dev:           {stats1['std']:20.6f} vs {stats2['std']:.6f}")
    print()
    
    # 3. Waveform differences
    print("3. WAVEFORM DIFFERENCE ANALYSIS")
    print("-" * 80)
    
    wave_diff = compute_waveform_difference(audio1, audio2)
    
    print(f"Mean Absolute Difference:  {wave_diff['mean_absolute_difference']:.8f}")
    print(f"Max Absolute Difference:   {wave_diff['max_absolute_difference']:.8f}")
    print(f"RMS Difference:            {wave_diff['rms_difference']:.8f}")
    print(f"SNR:                       {wave_diff['snr_db']:.2f} dB")
    print(f"PSNR:                      {wave_diff['psnr_db']:.2f} dB")
    print(f"Waveform Correlation:      {wave_diff['waveform_correlation']:.8f} ({wave_diff['waveform_similarity_percent']:.4f}%)")
    print(f"Identical Samples:         {wave_diff['samples_identical']:,} / {wave_diff['samples_total']:,} ({wave_diff['percent_identical']:.2f}%)")
    print()
    
    # 4. Spectral differences
    print("4. SPECTRAL DIFFERENCE ANALYSIS")
    print("-" * 80)
    
    spec_diff = compute_spectral_difference(audio1, audio2)
    
    print(f"Spectral Correlation:      {spec_diff['spectral_correlation']:.8f} ({spec_diff['spectral_similarity_percent']:.4f}%)")
    print(f"Mean Spectral Difference:  {spec_diff['mean_spectral_difference']:.8f}")
    print(f"Max Spectral Difference:   {spec_diff['max_spectral_difference']:.8f}")
    print(f"Mean Spectral Diff (dB):   {spec_diff['mean_spectral_difference_db']:.2f} dB")
    print()
    print("Frequency Band Differences (low to high):")
    for i, diff in enumerate(spec_diff['frequency_band_differences']):
        print(f"  Band {i+1:2d}: {diff:.8f}")
    print()
    
    # 5. Interpretation
    print("5. INTERPRETATION")
    print("=" * 80)
    
    if wave_diff['waveform_correlation'] > 0.9999:
        print("✅ EXTREMELY SIMILAR: Correlation > 99.99%")
        print("   → Precision difference is negligible")
    elif wave_diff['waveform_correlation'] > 0.999:
        print("⚠️  VERY SIMILAR: Correlation > 99.9%")
        print("   → Minor differences, likely inaudible")
    elif wave_diff['waveform_correlation'] > 0.99:
        print("⚠️  SIMILAR: Correlation > 99%")
        print("   → Small differences, might be audible in critical listening")
    else:
        print("❌ SIGNIFICANT DIFFERENCES: Correlation < 99%")
        print("   → Noticeable differences, precision matters")
    
    print()
    
    if wave_diff['snr_db'] > 60:
        print(f"✅ EXCELLENT SNR: {wave_diff['snr_db']:.1f} dB (difference is noise-floor level)")
    elif wave_diff['snr_db'] > 40:
        print(f"⚠️  GOOD SNR: {wave_diff['snr_db']:.1f} dB (minor audible difference possible)")
    else:
        print(f"❌ LOW SNR: {wave_diff['snr_db']:.1f} dB (significant audible difference)")
    
    print()
    print("=" * 80)
    
    # 6. Generate plots
    output_plot = Path(f"comparison_{audio1.stem}_vs_{audio2.stem}.png")
    generate_comparison_plot(audio1, audio2, output_plot)
    
    # Save detailed report
    report = {
        "files": {
            "bfloat16": str(audio1),
            "float32": str(audio2)
        },
        "ffprobe": {
            "bfloat16": probe1,
            "float32": probe2
        },
        "waveform_stats": {
            "bfloat16": stats1,
            "float32": stats2
        },
        "differences": {
            "waveform": wave_diff,
            "spectral": spec_diff
        }
    }
    
    report_path = Path(f"comparison_{audio1.stem}_vs_{audio2.stem}.json")
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"📄 Detailed report saved to: {report_path}")
    print()

if __name__ == "__main__":
    main()