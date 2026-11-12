"""T17.5: one request has its own bound on the number of files and their total size."""

import io

import pytest
from fastapi import HTTPException, UploadFile

from src.domain.uploads import UploadBatchLimits, UploadRejected, check_upload_batch
from src.services.file_reader import settings, validate_upload_batch

LIMITS = UploadBatchLimits(max_files=2, max_total_bytes=100)


@pytest.mark.parametrize("sizes", [[], [100], [50, 50], [0, 0]])
def test_batch_within_limits_is_admitted(sizes):
    check_upload_batch(sizes, LIMITS)


def test_more_files_than_allowed_is_rejected():
    with pytest.raises(UploadRejected) as rejected:
        check_upload_batch([1, 1, 1], LIMITS)
    assert rejected.value.code == "batch_files"
    assert "не больше 2" in str(rejected.value)


def test_total_size_over_limit_is_rejected():
    with pytest.raises(UploadRejected) as rejected:
        check_upload_batch([60, 41], UploadBatchLimits(max_files=5, max_total_bytes=100))
    assert rejected.value.code == "batch_size"


def test_file_count_is_reported_before_total_size():
    with pytest.raises(UploadRejected) as rejected:
        check_upload_batch([100, 100, 100], LIMITS)
    assert rejected.value.code == "batch_files"


def test_total_size_message_is_in_megabytes():
    limits = UploadBatchLimits(max_files=5, max_total_bytes=3 * 1024 * 1024)
    with pytest.raises(UploadRejected) as rejected:
        check_upload_batch([3 * 1024 * 1024 + 1], limits)
    assert "3 МБ" in str(rejected.value)


@pytest.mark.parametrize(
    "bad",
    [
        {"max_files": 0, "max_total_bytes": 1},
        {"max_files": 1, "max_total_bytes": 0},
        {"max_files": True, "max_total_bytes": 1},
    ],
)
def test_limits_must_be_positive_integers(bad):
    with pytest.raises(ValueError):
        UploadBatchLimits(**bad)


def _upload(size: int | None) -> UploadFile:
    return UploadFile(file=io.BytesIO(b""), filename="f.txt", size=size)


def test_validate_upload_batch_maps_rejection_to_413(monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_MAX_FILES", 1)
    with pytest.raises(HTTPException) as refused:
        validate_upload_batch([_upload(1), _upload(1)])
    assert refused.value.status_code == 413


def test_unknown_size_counts_as_the_per_file_maximum(monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_MAX_MB", 1)
    monkeypatch.setattr(settings, "UPLOAD_MAX_REQUEST_MB", 1)
    validate_upload_batch([_upload(None)])
    with pytest.raises(HTTPException) as refused:
        validate_upload_batch([_upload(None), _upload(None)])
    assert refused.value.status_code == 413
