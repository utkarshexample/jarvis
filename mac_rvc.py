"""Pi-side: convert a WAV through the Mac's RVC service (Gradio, port 7866).

The Mac runs RVC WebUI (Gradio) with the rick.pth model. This script
calls its /infer_convert endpoint programmatically from the Pi over
Tailscale -- no browser, no UI.

Usage (on the Pi):
  # 1. See what the Mac service exposes:
  python mac_rvc.py --list
  # 2. Convert a Piper WAV to the Rick voice:
  python mac_rvc.py in.wav out.wav

Endpoint (verified against the Mac's live API spec):
  /infer_convert(sid, input_audio_path, f0_up_key, f0_file, f0_method,
                 file_index, file_index2, index_rate, filter_radius,
                 resample_sr, rms_mix_rate, protect)
    -> (output_information, export_audio_filepath)
  sid=0 (rick.pth is the only model), f0_method=rmvpe, file_index2=rick.index.

Notes:
- MAC URL uses the Mac's TAILSCALE IP (100.123.112.57), not 127.0.0.1.
  (127.0.0.1 on the Pi means the Pi itself.)
- The Mac service must listen on 0.0.0.0:7866 (not 127.0.0.1 only),
  or the Pi cannot reach it.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys

MAC_URL = os.environ.get("MAC_RVC_URL", "http://100.123.112.57:7866/")
RVC_ENDPOINT = os.environ.get("RVC_ENDPOINT", "/infer_convert")
# The rick.index path, as the Mac service's own API spec reports it.
RVC_INDEX = os.environ.get(
    "RVC_INDEX",
    "/Users/utkarshaman/Documents/Coding/RVC_Web_UI/rvc-webui-macos/assets/indices/rick.index",
)


def _client():
    try:
        from gradio_client import Client
    except ImportError:
        print(
            "gradio_client is not installed. Run:\n"
            "  ~/.venvs/jarvis-runtime/bin/pip install gradio_client",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return Client(MAC_URL)


def list_endpoints() -> None:
    client = _client()
    print(f"Mac service: {MAC_URL}")
    print("Available endpoints (use one as RVC_ENDPOINT):")
    try:
        api = client.view_api(return_format="dict")
        for name in api.get("named_endpoints", {}):
            print(f"  {name}")
    except Exception as exc:  # noqa: BLE001 - discovery is best-effort
        print(f"Could not fetch the API spec ({exc}). Raw view:")
        print(client.view_api())


def convert(in_wav: str, out_wav: str) -> None:
    client = _client()
    print(f"Converting {in_wav} via {MAC_URL} (endpoint {RVC_ENDPOINT})...")
    result = client.predict(
        0,          # sid: rick.pth is the only model (index 0)
        in_wav,     # input_audio_path
        0,          # f0_up_key: no pitch shift
        "",        # f0_file: empty (extract F0 from the audio)
        "pm",       # f0_method: pm needs no ML model (rmvpe failed on the Mac)
        "",        # file_index: empty (use the dropdown below)
        RVC_INDEX,  # file_index2: the rick.index path
        0.75,       # index_rate
        4,          # filter_radius
        0,          # resample_sr: no resampling
        0.35,       # rms_mix_rate
        0.25,       # protect
        api_name=RVC_ENDPOINT,
    )
    # /infer_convert returns (output_information, export_audio_filepath).
    if not isinstance(result, (list, tuple)) or len(result) < 2:
        print(f"Unexpected result from the Mac service: {result!r}", file=sys.stderr)
        raise SystemExit(2)
    info, audio_path = result[0], result[1]
    print(f"Mac says: {info}")
    if not isinstance(audio_path, str) or not audio_path:
        print(f"No audio file in the result: {result!r}", file=sys.stderr)
        raise SystemExit(2)
    # The returned path is a local temp file (gradio_client downloads it).
    shutil.copyfile(audio_path, out_wav)
    print(f"Wrote {out_wav} ({os.path.getsize(out_wav)} bytes)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert a WAV via the Mac RVC service.")
    parser.add_argument("--list", action="store_true", help="list the Mac service endpoints and exit")
    parser.add_argument("input", nargs="?", help="input WAV (Piper output)")
    parser.add_argument("output", nargs="?", help="output WAV (Rick voice)")
    args = parser.parse_args()
    if args.list:
        list_endpoints()
        return
    if not args.input or not args.output:
        parser.error("need INPUT and OUTPUT wav paths (or --list)")
    convert(args.input, args.output)


if __name__ == "__main__":
    main()
