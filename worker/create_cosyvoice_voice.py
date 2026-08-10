"""Create a CosyVoice cloned voice explicitly from a public audio URL.

This command is intentionally separate from synthesis so normal worker runs
can never create voices as a side effect.
"""
from __future__ import annotations

import argparse
import json
import os

import httpx
from dotenv import load_dotenv


def _endpoint() -> str:
    explicit = os.environ.get("DASHSCOPE_CUSTOMIZATION_ENDPOINT", "").strip()
    if explicit:
        return explicit
    workspace = os.environ.get("DASHSCOPE_WORKSPACE_ID", "").strip()
    region = os.environ.get("DASHSCOPE_REGION", "cn-beijing").strip()
    if not workspace:
        raise SystemExit("DASHSCOPE_WORKSPACE_ID is required")
    return (
        f"https://{workspace}.{region}.maas.aliyuncs.com"
        "/api/v1/services/audio/tts/customization"
    )


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Create a CosyVoice cloned voice")
    parser.add_argument("--audio-url", required=True, help="Public HTTPS URL of the sample")
    parser.add_argument("--prefix", required=True, help="Voice name prefix")
    parser.add_argument(
        "--target-model",
        default=os.environ.get("DASHSCOPE_CLONE_TARGET_MODEL", "").strip()
        or os.environ.get("DASHSCOPE_MODEL", "").strip(),
    )
    args = parser.parse_args()
    api_key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("DASHSCOPE_API_KEY is required")
    if not args.target_model:
        raise SystemExit("--target-model or DASHSCOPE_CLONE_TARGET_MODEL is required")

    payload = {
        "model": "voice-enrollment",
        "input": {
            "action": "create_voice",
            "target_model": args.target_model,
            "prefix": args.prefix,
            "url": args.audio_url,
        },
    }
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        response = client.post(
            _endpoint(),
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
        )
    if response.is_error:
        raise SystemExit(f"voice creation failed ({response.status_code}): {response.text[:1000]}")
    result = response.json()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    voice_id = result.get("output", {}).get("voice_id")
    if voice_id:
        print(f"VOICE_ID={voice_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
