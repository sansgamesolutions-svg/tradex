from __future__ import annotations

from tradex.auto.types import ExecutionMode
from tradex.drill.broker import SimulatedBroker
from tradex.execution.models import OrderRequest


class BrokerRouter:
    """Automation broker router that fails closed for non-simulated execution."""

    def __init__(self, execution_mode: ExecutionMode = "SIMULATED") -> None:
        self.execution_mode = execution_mode

    def create(self, request: OrderRequest) -> SimulatedBroker:
        if self.execution_mode != "SIMULATED":
            raise RuntimeError(
                f"Automatic trading execution mode {self.execution_mode} is disabled in v1"
            )
        return SimulatedBroker()
