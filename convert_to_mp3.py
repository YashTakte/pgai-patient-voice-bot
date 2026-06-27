"""
convert_to_mp3.py
-----------------
Converts every recordings/*.wav into mp3, since the submission requires the
audio in mp3 or ogg format. Run this once after your calls:

    python convert_to_mp3.py

Uses a bundled ffmpeg (imageio-ffmpeg) so you don't need ffmpeg installed
system-wide on Windows. If the libraries aren't available it tells you what
to install; the .wav files are still valid recordings either way.
"""

import glob
import os


def main():
    wavs = glob.glob("recordings/*.wav")
    if not wavs:
        print("No .wav recordings found in recordings/.")
        return

    try:
        from pydub import AudioSegment
        import imageio_ffmpeg

        AudioSegment.converter = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as e:
        print(
            f"Could not load audio libraries ({e}).\n"
            "Install them with:  pip install pydub imageio-ffmpeg"
        )
        return

    for wav in wavs:
        mp3 = wav.replace(".wav", ".mp3")
        if os.path.exists(mp3):
            continue
        try:
            AudioSegment.from_wav(wav).export(mp3, format="mp3")
            print(f"Converted {wav} -> {mp3}")
        except Exception as e:
            print(f"Failed to convert {wav}: {e}")

    print("Done.")


if __name__ == "__main__":
    main()
