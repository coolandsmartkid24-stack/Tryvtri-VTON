"""Tests for GPU pod endpoint discovery and the no-spend compliance guard."""

import pytest

from backend.app.config import get_settings, reset_settings_cache
from backend.app.services.gpu_manager import GpuManager, _is_pod_running, _pod_public_endpoint
import os


@pytest.fixture
def settings():
    reset_settings_cache()
    s = get_settings()
    yield s
    reset_settings_cache()


def _pod(ports_mapping=None, ssh_cmd=None, **extra):
    pod = {"status": "RUNNING"}
    if ports_mapping is not None:
        pod["ports_mapping"] = ports_mapping
    if ssh_cmd is not None:
        pod["ssh_connect_cmd"] = ssh_cmd
    pod.update(extra)
    return pod


class TestPodStatusParsing:
    def test_accepts_uppercase_lium_status(self):
        assert _is_pod_running("RUNNING") is True
        assert _is_pod_running("PENDING") is False
        assert _is_pod_running("FAILED") is False
        assert _is_pod_running(None) is False
        assert _is_pod_running("running") is True


class TestPodPublicEndpoint:
    def test_mapped_pod_port_8888_to_40398(self, settings):
        pod = _pod(ports_mapping={"8888": 40398}, ssh_cmd="ssh root@203.0.113.7 -p 4022 -o StrictHostKeyChecking=no")
        settings.lium_inference_port = 8888
        assert _pod_public_endpoint(pod, settings) == "http://203.0.113.7:40398"

    def test_json_string_ports_mapping(self, settings):
        pod = _pod(ports_mapping='{"8888": 40398}', ssh_cmd="ssh root@203.0.113.7 -p 4022")
        settings.lium_inference_port = 8888
        assert _pod_public_endpoint(pod, settings) == "http://203.0.113.7:40398"

    def test_single_exposed_port_without_explicit_service_port(self, settings):
        pod = _pod(ports_mapping={"9001": 41000}, ssh_cmd="root@203.0.113.9 -p 4010")
        settings.lium_inference_port = 8000
        assert _pod_public_endpoint(pod, settings) == "http://203.0.113.9:41000"

    def test_missing_mapping_falls_back_to_ip_and_config_port(self, settings):
        pod = _pod(ip="203.0.113.5")
        settings.lium_inference_port = 8888
        assert _pod_public_endpoint(pod, settings) == "http://203.0.113.5:8888"

    def test_unresolvable_pod_returns_none(self, settings):
        pod = _pod(ports_mapping={}, ssh_cmd="")
        settings.lium_inference_port = 8888
        assert _pod_public_endpoint(pod, settings) is None


class TestGpuPauseGuard:
    @pytest.mark.asyncio
    async def test_paused_start_gpu_never_starts_and_never_spends(self, settings):
        os.environ["GPU_CALL_PAUSED"] = "true"
        reset_settings_cache()
        mgr = GpuManager()  # mock_mode=False, like production
        try:
            with pytest.raises(Exception, match="paused"):
                await mgr.start_gpu()
            assert mgr.status == "stopped"
            assert mgr.pod_id is None
            assert mgr._inference_endpoint is None
        finally:
            os.environ.pop("GPU_CALL_PAUSED", None)
            reset_settings_cache()
