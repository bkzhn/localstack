from __future__ import annotations

import abc
from typing import Optional

from localstack.aws.api.stepfunctions import HistoryEventType, TaskTimedOutEventDetails
from localstack.services.stepfunctions.asl.component.common.error_name.failure_event import (
    FailureEvent,
)
from localstack.services.stepfunctions.asl.component.common.error_name.states_error_name import (
    StatesErrorName,
)
from localstack.services.stepfunctions.asl.component.common.error_name.states_error_name_type import (
    StatesErrorNameType,
)
from localstack.services.stepfunctions.asl.component.common.parargs import Parargs
from localstack.services.stepfunctions.asl.component.state.state_execution.execute_state import (
    ExecutionState,
)
from localstack.services.stepfunctions.asl.component.state.state_execution.state_task.credentials import (
    Credentials,
    StateCredentials,
)
from localstack.services.stepfunctions.asl.component.state.state_execution.state_task.service.resource import (
    Resource,
)
from localstack.services.stepfunctions.asl.component.state.state_props import StateProps
from localstack.services.stepfunctions.asl.eval.environment import Environment
from localstack.services.stepfunctions.asl.eval.event.event_detail import EventDetails


class StateTask(ExecutionState, abc.ABC):
    resource: Resource
    parargs: Optional[Parargs]
    credentials: Optional[Credentials]

    def __init__(self):
        super(StateTask, self).__init__(
            state_entered_event_type=HistoryEventType.TaskStateEntered,
            state_exited_event_type=HistoryEventType.TaskStateExited,
        )

    def from_state_props(self, state_props: StateProps) -> None:
        super(StateTask, self).from_state_props(state_props)
        self.resource = state_props.get(Resource)
        self.parargs = state_props.get(Parargs)
        self.credentials = state_props.get(Credentials)

    def _get_supported_parameters(self) -> Optional[set[str]]:  # noqa
        return None

    def _eval_parameters(self, env: Environment) -> dict:
        # Eval raw parameters.
        parameters = dict()
        if self.parargs is not None:
            self.parargs.eval(env=env)
            parameters = env.stack.pop()

        # Handle supported parameters.
        supported_parameters = self._get_supported_parameters()
        if supported_parameters:
            unsupported_parameters: list[str] = [
                parameter
                for parameter in parameters.keys()
                if parameter not in supported_parameters
            ]
            for unsupported_parameter in unsupported_parameters:
                parameters.pop(unsupported_parameter, None)

        return parameters

    def _eval_state_credentials(self, env: Environment) -> StateCredentials:
        if not self.credentials:
            state_credentials = StateCredentials(role_arn=env.aws_execution_details.role_arn)
        else:
            self.credentials.eval(env=env)
            state_credentials = env.stack.pop()
        return state_credentials

    def _get_timed_out_failure_event(self, env: Environment) -> FailureEvent:
        return FailureEvent(
            env=env,
            error_name=StatesErrorName(typ=StatesErrorNameType.StatesTimeout),
            event_type=HistoryEventType.TaskTimedOut,
            event_details=EventDetails(
                taskTimedOutEventDetails=TaskTimedOutEventDetails(
                    error=StatesErrorNameType.StatesTimeout.to_name(),
                )
            ),
        )

    def _from_error(self, env: Environment, ex: Exception) -> FailureEvent:
        if isinstance(ex, TimeoutError):
            return self._get_timed_out_failure_event(env)
        return super()._from_error(env=env, ex=ex)
