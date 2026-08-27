"""Many communities at once: the queue, the scheduler and the worker pool.

Everything under `dcr/` outside this package researches ONE community. This
package is what turns that into a run of two hundred and twelve of them without
the researcher sitting at the keyboard between each one (brief §2, §6, §7).

    RunStore        the run-level database: the queue, and nothing else
    plan            what the researcher entered, sized and ordered
    scheduler       who runs next, and how many at once
    governor        how many workers this machine can actually carry
    hosts           per-host politeness ACROSS communities
    pool            the worker processes, and surviving their deaths
    worker          the child process: one community, start to workbook
    events          what a worker tells the scheduler while it works
    dashboard       what the researcher sees
    recovery        picking a run back up after the machine was switched off
"""

from .events import EventKind, WorkerEvent
from .plan import CommunityJob, RunPlan, estimate_workload
from .store import JOB_STATES, RunStore

__all__ = [
    "CommunityJob", "EventKind", "JOB_STATES", "RunPlan", "RunStore",
    "WorkerEvent", "estimate_workload",
]
