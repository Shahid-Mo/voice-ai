"""
Audio format conversion utilities.

Converts between transport formats (μ-law, WebM, etc.) and our internal
PCM linear16 16kHz mono format used by Deepgram STT/TTS.

Uses NumPy + scipy for audio processing (modern, maintained, no deprecation warnings).
"""

import numpy as np
from scipy import signal


def mulaw_to_pcm_16k(mulaw_data: bytes, input_rate: int = 8000) -> bytes:
    """
    Convert μ-law audio to PCM linear16 16kHz mono.

    Used for phone audio (Twilio) which sends μ-law 8kHz.

    Args:
        mulaw_data: μ-law encoded audio bytes
        input_rate: Input sample rate (8000 for phone, 16000 for some systems)

    Returns:
        bytes: PCM linear16 16kHz mono (ready for Deepgram STT)

    Example:
        >>> phone_audio = receive_from_twilio()
        >>> pcm = mulaw_to_pcm_16k(phone_audio)
        >>> await stt.transcribe_stream(pcm, ...)
    """
    # Decode μ-law to linear PCM int16
    pcm_samples = _mulaw_decode(mulaw_data)

    # Resample if needed (8kHz → 16kHz)
    if input_rate != 16000:
        pcm_samples = _resample(pcm_samples, input_rate, 16000)

    # Convert back to bytes
    return pcm_samples.astype(np.int16).tobytes()


def pcm_16k_to_mulaw(pcm_data: bytes, output_rate: int = 8000) -> bytes:
    """
    Convert PCM linear16 16kHz mono to μ-law audio.

    Used for phone audio output (Twilio expects μ-law 8kHz).

    Args:
        pcm_data: PCM linear16 16kHz mono (from Deepgram TTS)
        output_rate: Output sample rate (8000 for phone)

    Returns:
        bytes: μ-law encoded audio (ready for Twilio)

    Example:
        >>> pcm = await tts.synthesize(text)
        >>> phone_audio = pcm_16k_to_mulaw(pcm)
        >>> await send_to_twilio(phone_audio)
    """
    # Convert bytes to int16 array
    pcm_samples = np.frombuffer(pcm_data, dtype=np.int16)

    # Resample if needed (16kHz → 8kHz)
    if output_rate != 16000:
        pcm_samples = _resample(pcm_samples, 16000, output_rate)

    # Encode to μ-law
    mulaw_bytes = _mulaw_encode(pcm_samples)

    return mulaw_bytes


def _mulaw_decode(mulaw_bytes: bytes) -> np.ndarray:
    """
    Decode μ-law (G.711) to linear PCM int16.

    μ-law is a logarithmic compression used in telephony (US/Japan).

    Args:
        mulaw_bytes: μ-law encoded bytes (8-bit samples)

    Returns:
        np.ndarray: Linear PCM samples (int16)
    """
    # Convert to uint8 array
    mulaw = np.frombuffer(mulaw_bytes, dtype=np.uint8)

    # G.711 μ-law decode lookup (ITU-T G.711)
    # This is the standard μ-law decompression algorithm
    mulaw = mulaw.astype(np.int32)

    # Invert bits (μ-law encoding inverts for transmission)
    mulaw = ~mulaw & 0xFF

    # Extract sign, exponent, mantissa
    sign = (mulaw & 0x80) >> 7
    exponent = (mulaw & 0x70) >> 4
    mantissa = mulaw & 0x0F

    # Decode using μ-law formula
    # Linear value = (33 + 2*mantissa) * 2^exponent - 33
    linear = ((mantissa << 3) + 0x84) << exponent
    linear = linear - 0x84

    # Apply sign
    linear = np.where(sign == 0, linear, -linear)

    # Scale to int16 range
    return linear.astype(np.int16)


def _mulaw_encode(pcm_samples: np.ndarray) -> bytes:
    """
    Encode linear PCM int16 to μ-law (G.711).

    Args:
        pcm_samples: Linear PCM samples (int16)

    Returns:
        bytes: μ-law encoded bytes (8-bit samples)
    """
    # Ensure int32 for calculations
    pcm = pcm_samples.astype(np.int32)

    # Extract sign
    sign = (pcm < 0).astype(np.int32)

    # Work with absolute value
    pcm = np.abs(pcm)

    # Add bias (33) and clip
    pcm = np.clip(pcm + 33, 0, 32767)

    # Find exponent (position of highest set bit)
    exponent = np.zeros_like(pcm)
    for i in range(7, -1, -1):
        mask = pcm >= (1 << (i + 7))
        exponent = np.where(mask & (exponent == 0), i, exponent)

    # Extract mantissa (4 bits after exponent)
    mantissa = (pcm >> (exponent + 3)) & 0x0F

    # Combine: sign (1 bit) + exponent (3 bits) + mantissa (4 bits)
    mulaw = (sign << 7) | (exponent << 4) | mantissa

    # Invert bits (μ-law standard)
    mulaw = ~mulaw & 0xFF

    return mulaw.astype(np.uint8).tobytes()


def _resample(samples: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    """
    Resample audio using high-quality polyphase filtering.

    Uses scipy's resample_poly which is efficient for integer ratios.

    Args:
        samples: Input audio samples (int16 or float)
        src_rate: Source sample rate (Hz)
        dst_rate: Destination sample rate (Hz)

    Returns:
        np.ndarray: Resampled audio (same dtype as input)
    """
    if src_rate == dst_rate:
        return samples

    # Calculate resampling ratio
    # For 8kHz → 16kHz: up=2, down=1
    # For 16kHz → 8kHz: up=1, down=2
    from math import gcd

    divisor = gcd(src_rate, dst_rate)
    up = dst_rate // divisor
    down = src_rate // divisor

    # Convert to float for processing
    dtype = samples.dtype
    samples_float = samples.astype(np.float32)

    # Resample using polyphase filtering (high quality, efficient)
    resampled = signal.resample_poly(samples_float, up, down)

    # Convert back to original dtype
    return resampled.astype(dtype)


# TODO: Add when we build browser support
# def webm_to_pcm_16k(webm_data: bytes) -> bytes:
#     """Convert WebM/Opus to PCM 16kHz mono (for browser audio)."""
#     # Use pydub or ffmpeg
#     pass
