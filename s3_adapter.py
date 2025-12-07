# s3_adapter.py
import boto3
import os
import io
import logging
from botocore.exceptions import ClientError

class S3Blob:
    def __init__(self, bucket, name, s3_client):
        self.bucket = bucket
        self.name = name
        self.s3 = s3_client
        self.content_type = None

    def upload_from_string(self, data, content_type=None):
        params = {'Bucket': self.bucket.name, 'Key': self.name, 'Body': data}
        if content_type:
            params['ContentType'] = content_type
        self.s3.put_object(**params)

    def upload_from_file(self, file_obj, content_type=None):
        extra_args = {}
        if content_type:
            extra_args['ContentType'] = content_type
        # Ensure we are at the start of the file
        if hasattr(file_obj, 'seek'):
            file_obj.seek(0)
        self.s3.upload_fileobj(file_obj, self.bucket.name, self.name, ExtraArgs=extra_args)

    def download_as_bytes(self):
        response = self.s3.get_object(Bucket=self.bucket.name, Key=self.name)
        return response['Body'].read()

    def download_to_file(self, file_obj):
        self.s3.download_fileobj(self.bucket.name, self.name, file_obj)

    def exists(self):
        try:
            self.s3.head_object(Bucket=self.bucket.name, Key=self.name)
            return True
        except ClientError:
            return False

    def delete(self):
        self.s3.delete_object(Bucket=self.bucket.name, Key=self.name)

class S3Bucket:
    def __init__(self, name, s3_client):
        self.name = name
        self.s3 = s3_client

    def blob(self, blob_name):
        return S3Blob(self, blob_name, self.s3)

    def reload(self):
        # S3 buckets don't need 'reloading', this is just for compatibility
        pass

    def delete_blobs(self, blobs, on_error=None):
        # Batch delete for S3
        if not blobs:
            return
        
        objects_to_delete = [{'Key': blob.name} for blob in blobs]
        # S3 delete_objects can handle max 1000 keys
        try:
            self.s3.delete_objects(
                Bucket=self.name,
                Delete={'Objects': objects_to_delete}
            )
        except Exception as e:
            if on_error:
                on_error(e)
            else:
                logging.error(f"Failed to batch delete blobs: {e}")

class S3Client:
    def __init__(self):
        self.s3 = boto3.client(
            's3',
            endpoint_url=os.environ.get("S3_ENDPOINT_URL"),
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY")
        )

    def bucket(self, bucket_name):
        return S3Bucket(bucket_name, self.s3)

    def list_blobs(self, bucket_or_name, prefix=None):
        bucket_name = bucket_or_name.name if isinstance(bucket_or_name, S3Bucket) else bucket_or_name
        paginator = self.s3.get_paginator('list_objects_v2')
        page_iterator = paginator.paginate(Bucket=bucket_name, Prefix=prefix or "")

        for page in page_iterator:
            if 'Contents' in page:
                for obj in page['Contents']:
                    yield S3Blob(S3Bucket(bucket_name, self.s3), obj['Key'], self.s3)