"""Bounded resource snapshots for the existing draft worker."""
import ctypes
import os
from ctypes import wintypes
from datetime import datetime, timezone

from agentforge.ops import discovery

MIB = 1024 * 1024
MIN_RAM_MIB = {"plan": 4096, "cast": 4096, "storyboard": 4096, "image": 4096, "render": 2048}
MIN_VRAM_MIB = {"plan": 6144, "cast": 6144, "storyboard": 6144, "image": 2048}
GPU_FLOORS = {"image": (4096, 8192, 3072), "motion": (8192, 12288, 6144),
              "ltx": (12288, 16384, 8192)}


class ResourceBlocked(ValueError):
    """GPU admission failed or the provider reported resource exhaustion."""


class ResourceWait(Exception):
    """An existing Studio worker must wait for runtime resources."""


class NeedsReconciliation(ValueError):
    """A possibly dispatched job must be reconciled before any new submission."""


def require_gpu(operation, sample=None, *, min_commit_mib=0):
    """Conservative admission floors in MiB, not estimates of peak consumption."""
    sample = snapshot() if sample is None else sample
    ram = sample.get("ram_available")
    used, limit = sample.get("commit_used"), sample.get("commit_limit")
    commit = None if used is None or limit is None else limit - used
    readings = (ram / MIB if ram is not None else None,
                commit / MIB if commit is not None else None, sample.get("vram_free_mib"))
    for name, value, floor in zip(("RAM", "COMMIT", "VRAM"), readings, GPU_FLOORS[operation]):
        if name == "COMMIT" and os.name != "nt":
            continue
        if name == "COMMIT":
            floor = max(floor, min_commit_mib)
        key = f"AGENTFORGE_{operation.upper()}_MIN_{name}_MIB"
        try:
            floor = max(floor, int(os.environ.get(key, floor)))
        except ValueError:
            raise ResourceBlocked(f"Invalid resource threshold: {key}") from None
        if value is None:
            raise ResourceBlocked(name + "_UNAVAILABLE")
        if value < floor:
            raise ResourceBlocked(name + "_LOW")


def provider_memory_error(status):
    if not isinstance(status, dict):
        return False
    messages = status.get("messages")
    if not isinstance(messages, list):
        return False
    return any(
        isinstance(row, list) and len(row) > 1 and row[0] == "execution_error"
        and isinstance(row[1], dict)
        and any(marker in str(row[1].get("exception_message", "")).lower() for marker in (
            "out of memory", "hostbuffer.read_file_slice failed", "paging file",
            "insufficient system resources",
        ))
        for row in messages
    )


def _windows_commit():
    if os.name != "nt":
        return None, None

    class PerformanceInfo(ctypes.Structure):
        _fields_ = [("size", ctypes.c_ulong)] + [
            (key, ctypes.c_size_t) for key in (
                "commit_total", "commit_limit", "commit_peak", "physical_total",
                "physical_available", "system_cache", "kernel_total", "kernel_paged",
                "kernel_nonpaged", "page_size")
        ] + [(key, ctypes.c_ulong) for key in ("handles", "processes", "threads")]

    info = PerformanceInfo()
    info.size = ctypes.sizeof(info)
    if ctypes.windll.psapi.GetPerformanceInfo(ctypes.byref(info), info.size):
        return info.commit_total * info.page_size, info.commit_limit * info.page_size
    return None, None


def _windows_processes():
    if os.name != "nt":
        return {}

    class MemoryCounters(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("faults", wintypes.DWORD)] + [
            (key, ctypes.c_size_t) for key in ("peak_working", "working", "paged_peak",
                "paged", "nonpaged_peak", "nonpaged", "pagefile", "pagefile_peak", "private")]

    kernel = ctypes.windll.kernel32
    process_list = (wintypes.DWORD * 8192)()
    returned = wintypes.DWORD()
    if not ctypes.windll.psapi.EnumProcesses(process_list, ctypes.sizeof(process_list), ctypes.byref(returned)):
        return {}
    result = {}
    # Explicit handle types keep the process handle correctly sized on 64-bit Windows.
    kernel.OpenProcess.restype = wintypes.HANDLE
    buffer = ctypes.create_unicode_buffer(4096)
    for pid in process_list[:returned.value // ctypes.sizeof(wintypes.DWORD)]:
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            continue
        handle = wintypes.HANDLE(handle)
        try:
            length = wintypes.DWORD(len(buffer))
            if not kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(length)):
                continue
            path = buffer.value.lower()
            name = os.path.basename(path)
            role = ("agentforge" if pid == os.getpid() else
                    "ollama" if name.startswith(("ollama", "llama-server")) and "ollama" in path else
                    "ffmpeg" if name.startswith("ffmpeg") else
                    "comfyui" if "comfyui" in path and name.startswith("python") else None)
            if not role:
                continue
            counters = MemoryCounters()
            counters.size = ctypes.sizeof(counters)
            if ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.size):
                result.setdefault(role, []).append({"pid": pid, "working_bytes": counters.working,
                                                    "private_bytes": counters.private})
        finally:
            kernel.CloseHandle(handle)
    return result


def memory_snapshot():
    memory = discovery._memory()
    commit_used, commit_limit = _windows_commit()
    return {
        "ram_total": memory["total_bytes"], "ram_available": memory["available_bytes"],
        "commit_used": commit_used, "commit_limit": commit_limit,
    }


def snapshot():
    memory = memory_snapshot()
    devices = discovery._gpu()["devices"]
    device = devices[0] if len(devices) == 1 else {}
    return {
        "checked_at": datetime.now(timezone.utc).isoformat(), **memory,
        "vram_total_mib": device.get("vram_total_mib"), "vram_free_mib": device.get("vram_free_mib"),
        "processes": _windows_processes(),
    }


def pressure(sample, operation):
    budget = MIN_RAM_MIB.get(operation, MIN_RAM_MIB["image"]) * MIB
    available = sample["ram_available"]
    if available is not None and available < budget:
        return "RAM_LOW"
    use, limit = sample["commit_used"], sample["commit_limit"]
    if use is not None and limit is not None and limit - use < budget:
        return "COMMIT_LOW"
    free = sample["vram_free_mib"]
    if operation in MIN_VRAM_MIB and free is not None and free < MIN_VRAM_MIB[operation]:
        return "VRAM_LOW"
    return None


def can_release_models(sample):
    """Offloading GPU weights can allocate additional host memory."""
    available = sample["ram_available"]
    use, limit = sample["commit_used"], sample["commit_limit"]
    if available is None or available < 4096 * MIB:
        return False
    if os.name == "nt" and (use is None or limit is None):
        return False
    return use is None or limit is None or limit - use >= 8192 * MIB
