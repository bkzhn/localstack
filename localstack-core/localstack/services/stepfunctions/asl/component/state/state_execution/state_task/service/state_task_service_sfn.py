import json
from typing import Any, Callable, Final, Optional

from botocore.exceptions import ClientError

from localstack.aws.api.stepfunctions import (
    DescribeExecutionOutput,
    ExecutionStatus,
    HistoryEventType,
    TaskFailedEventDetails,
)
from localstack.services.stepfunctions.asl.component.common.error_name.custom_error_name import (
    CustomErrorName,
)
from localstack.services.stepfunctions.asl.component.common.error_name.failure_event import (
    FailureEvent,
    FailureEventException,
)
from localstack.services.stepfunctions.asl.component.common.error_name.states_error_name import (
    StatesErrorName,
)
from localstack.services.stepfunctions.asl.component.common.error_name.states_error_name_type import (
    StatesErrorNameType,
)
from localstack.services.stepfunctions.asl.component.state.state_execution.state_task.credentials import (
    StateCredentials,
)
from localstack.services.stepfunctions.asl.component.state.state_execution.state_task.service.resource import (
    ResourceCondition,
    ResourceRuntimePart,
)
from localstack.services.stepfunctions.asl.component.state.state_execution.state_task.service.state_task_service_callback import (
    StateTaskServiceCallback,
)
from localstack.services.stepfunctions.asl.eval.environment import Environment
from localstack.services.stepfunctions.asl.eval.event.event_detail import EventDetails
from localstack.services.stepfunctions.asl.utils.boto_client import boto_client_for
from localstack.services.stepfunctions.asl.utils.encoding import to_json_str
from localstack.utils.collections import select_from_typed_dict

_SUPPORTED_INTEGRATION_PATTERNS: Final[set[ResourceCondition]] = {
    ResourceCondition.WaitForTaskToken,
    ResourceCondition.Sync,
    ResourceCondition.Sync2,
}
_SUPPORTED_API_PARAM_BINDINGS: Final[dict[str, set[str]]] = {
    "startexecution": {"Input", "Name", "StateMachineArn"}
}


class StateTaskServiceSfn(StateTaskServiceCallback):
    def __init__(self):
        super().__init__(supported_integration_patterns=_SUPPORTED_INTEGRATION_PATTERNS)

    def _get_supported_parameters(self) -> Optional[set[str]]:
        return _SUPPORTED_API_PARAM_BINDINGS.get(self.resource.api_action.lower())

    def _from_error(self, env: Environment, ex: Exception) -> FailureEvent:
        if isinstance(ex, ClientError):
            error_code = ex.response["Error"]["Code"]
            error_name: str = f"StepFunctions.{error_code}Exception"
            error_cause_details = [
                "Service: AWSStepFunctions",
                f"Status Code: {ex.response['ResponseMetadata']['HTTPStatusCode']}",
                f"Error Code: {error_code}",
                f"Request ID: {ex.response['ResponseMetadata']['RequestId']}",
                "Proxy: null",  # TODO: investigate this proxy value.
            ]
            if "HostId" in ex.response["ResponseMetadata"]:
                error_cause_details.append(
                    f"Extended Request ID: {ex.response['ResponseMetadata']['HostId']}"
                )
            error_cause: str = (
                f"{ex.response['Error']['Message']} ({'; '.join(error_cause_details)})"
            )
            return FailureEvent(
                env=env,
                error_name=CustomErrorName(error_name),
                event_type=HistoryEventType.TaskFailed,
                event_details=EventDetails(
                    taskFailedEventDetails=TaskFailedEventDetails(
                        error=error_name,
                        cause=error_cause,
                        resource=self._get_sfn_resource(),
                        resourceType=self._get_sfn_resource_type(),
                    )
                ),
            )
        return super()._from_error(env=env, ex=ex)

    def _normalise_parameters(
        self,
        parameters: dict,
        boto_service_name: Optional[str] = None,
        service_action_name: Optional[str] = None,
    ) -> None:
        if service_action_name is None:
            if self._get_boto_service_action() == "start_execution":
                optional_input = parameters.get("Input")
                if not isinstance(optional_input, str):
                    # AWS Sfn's documentation states:
                    # If you don't include any JSON input data, you still must include the two braces.
                    if optional_input is None:
                        optional_input = {}
                    parameters["Input"] = to_json_str(optional_input, separators=(",", ":"))
        super()._normalise_parameters(
            parameters=parameters,
            boto_service_name=boto_service_name,
            service_action_name=service_action_name,
        )

    def _build_sync_resolver(
        self,
        env: Environment,
        resource_runtime_part: ResourceRuntimePart,
        normalised_parameters: dict,
        state_credentials: StateCredentials,
    ) -> Callable[[], Optional[Any]]:
        sfn_client = boto_client_for(
            service="stepfunctions",
            region=resource_runtime_part.region,
            state_credentials=state_credentials,
        )
        submission_output: dict = env.stack.pop()
        execution_arn: str = submission_output["ExecutionArn"]

        def _sync_resolver() -> Optional[Any]:
            describe_execution_output = sfn_client.describe_execution(executionArn=execution_arn)
            describe_execution_output: DescribeExecutionOutput = select_from_typed_dict(
                DescribeExecutionOutput, describe_execution_output
            )
            execution_status: ExecutionStatus = describe_execution_output["status"]

            if execution_status == ExecutionStatus.RUNNING:
                return None

            self._normalise_response(
                response=describe_execution_output, service_action_name="describe_execution"
            )
            if execution_status == ExecutionStatus.SUCCEEDED:
                return describe_execution_output
            else:
                raise FailureEventException(
                    FailureEvent(
                        env=env,
                        error_name=StatesErrorName(typ=StatesErrorNameType.StatesTaskFailed),
                        event_type=HistoryEventType.TaskFailed,
                        event_details=EventDetails(
                            taskFailedEventDetails=TaskFailedEventDetails(
                                resource=self._get_sfn_resource(),
                                resourceType=self._get_sfn_resource_type(),
                                error=StatesErrorNameType.StatesTaskFailed.to_name(),
                                cause=to_json_str(describe_execution_output),
                            )
                        ),
                    )
                )

        return _sync_resolver

    @staticmethod
    def _sync2_api_output_of(typ: type, value: json) -> None:
        def _replace_with_json_if_str(key: str) -> None:
            inner_value = value.get(key)
            if isinstance(inner_value, str):
                value[key] = json.loads(inner_value)

        match typ:
            case DescribeExecutionOutput:  # noqa
                _replace_with_json_if_str("input")
                _replace_with_json_if_str("output")

    def _build_sync2_resolver(
        self,
        env: Environment,
        resource_runtime_part: ResourceRuntimePart,
        normalised_parameters: dict,
        state_credentials: StateCredentials,
    ) -> Callable[[], Optional[Any]]:
        sfn_client = boto_client_for(
            region=resource_runtime_part.region,
            service="stepfunctions",
            state_credentials=state_credentials,
        )
        submission_output: dict = env.stack.pop()
        execution_arn: str = submission_output["ExecutionArn"]

        def _sync2_resolver() -> Optional[Any]:
            describe_execution_output = sfn_client.describe_execution(executionArn=execution_arn)
            describe_execution_output: DescribeExecutionOutput = select_from_typed_dict(
                DescribeExecutionOutput, describe_execution_output
            )
            execution_status: ExecutionStatus = describe_execution_output["status"]

            if execution_status == ExecutionStatus.RUNNING:
                return None

            self._sync2_api_output_of(typ=DescribeExecutionOutput, value=describe_execution_output)
            self._normalise_response(
                response=describe_execution_output, service_action_name="describe_execution"
            )
            if execution_status == ExecutionStatus.SUCCEEDED:
                return describe_execution_output
            else:
                raise FailureEventException(
                    FailureEvent(
                        env=env,
                        error_name=StatesErrorName(typ=StatesErrorNameType.StatesTaskFailed),
                        event_type=HistoryEventType.TaskFailed,
                        event_details=EventDetails(
                            taskFailedEventDetails=TaskFailedEventDetails(
                                resource=self._get_sfn_resource(),
                                resourceType=self._get_sfn_resource_type(),
                                error=StatesErrorNameType.StatesTaskFailed.to_name(),
                                cause=to_json_str(describe_execution_output),
                            )
                        ),
                    )
                )

        return _sync2_resolver

    def _eval_service_task(
        self,
        env: Environment,
        resource_runtime_part: ResourceRuntimePart,
        normalised_parameters: dict,
        state_credentials: StateCredentials,
    ):
        service_name = self._get_boto_service_name()
        api_action = self._get_boto_service_action()
        sfn_client = boto_client_for(
            region=resource_runtime_part.region,
            service=service_name,
            state_credentials=state_credentials,
        )
        response = getattr(sfn_client, api_action)(**normalised_parameters)
        response.pop("ResponseMetadata", None)
        env.stack.append(response)
