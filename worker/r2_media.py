"""Private R2 storage for generated task images and video."""
import os
import re
from functools import lru_cache


def media_path(path: str) -> bool:
    return bool(re.fullmatch(
        r'[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}/.+\.(?:png|jpe?g|webp|mp4)', path, re.I
    )) and '\\' not in path and not any(part in ('', '.', '..') for part in path.split('/'))


def enabled() -> bool:
    return bool(os.environ.get('R2_BUCKET'))


@lru_cache(maxsize=1)
def client():
    import boto3
    from botocore.config import Config
    account = os.environ['R2_ACCOUNT_ID'].strip()
    if not re.fullmatch(r'[a-fA-F0-9]{32}', account):
        raise ValueError('R2_ACCOUNT_ID 无效')
    return boto3.client(
        's3', endpoint_url=f'https://{account}.r2.cloudflarestorage.com',
        region_name='auto', aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],
        aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'],
        config=Config(s3={'addressing_style': 'path'}, request_checksum_calculation='when_required',
                      response_checksum_validation='when_required', retries={'mode': 'standard', 'total_max_attempts': 3}),
    )


def bucket() -> str:
    return os.environ['R2_BUCKET']


def info(path: str) -> dict | None:
    from botocore.exceptions import ClientError
    try:
        return client().head_object(Bucket=bucket(), Key=path)
    except ClientError as exc:
        if exc.response.get('ResponseMetadata', {}).get('HTTPStatusCode') == 404:
            return None
        raise


def upload_file(path: str, local_file: str, content_type: str, metadata: dict | None = None) -> None:
    extras = {'ContentType': content_type}
    if metadata:
        extras['Metadata'] = metadata
    client().upload_file(local_file, bucket(), path, ExtraArgs=extras)


def upload_bytes(path: str, data: bytes, content_type: str) -> None:
    client().put_object(Bucket=bucket(), Key=path, Body=data, ContentType=content_type)


def download_file(path: str, local_file: str) -> None:
    client().download_file(bucket(), path, local_file)


def remove(path: str) -> None:
    client().delete_object(Bucket=bucket(), Key=path)
