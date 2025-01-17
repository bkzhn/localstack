import json

from localstack.testing.pytest import markers
from localstack.testing.pytest.stepfunctions.utils import (
    create_and_record_execution,
)
from localstack.utils.strings import short_uid
from tests.aws.services.stepfunctions.templates.services.services_templates import (
    ServicesTemplates as ST,
)


@markers.snapshot.skip_snapshot_verify(
    paths=[
        # # TODO: add support for Sdk Http metadata.
        "$..SdkHttpMetadata",
        "$..SdkResponseMetadata",
    ]
)
class TestTaskServiceDynamoDB:
    @markers.aws.needs_fixing
    def test_put_get_item(
        self,
        aws_client,
        create_state_machine_iam_role,
        create_state_machine,
        dynamodb_create_table,
        sfn_snapshot,
    ):
        sfn_snapshot.add_transformer(sfn_snapshot.transform.dynamodb_api())

        table_name = f"sfn_test_table_{short_uid()}"
        dynamodb_create_table(table_name=table_name, partition_key="id", client=aws_client.dynamodb)

        template = ST.load_sfn_template(ST.DYNAMODB_PUT_GET_ITEM)
        definition = json.dumps(template)

        exec_input = json.dumps(
            {
                "TableName": table_name,
                "Item": {"data": {"S": "HelloWorld"}, "id": {"S": "id1"}},
                "Key": {"id": {"S": "id1"}},
            }
        )
        create_and_record_execution(
            aws_client,
            create_state_machine_iam_role,
            create_state_machine,
            sfn_snapshot,
            definition,
            exec_input,
        )

    @markers.aws.needs_fixing
    def test_put_delete_item(
        self,
        aws_client,
        create_state_machine_iam_role,
        create_state_machine,
        dynamodb_create_table,
        sfn_snapshot,
    ):
        sfn_snapshot.add_transformer(sfn_snapshot.transform.dynamodb_api())

        table_name = f"sfn_test_table_{short_uid()}"
        dynamodb_create_table(table_name=table_name, partition_key="id", client=aws_client.dynamodb)

        template = ST.load_sfn_template(ST.DYNAMODB_PUT_DELETE_ITEM)
        definition = json.dumps(template)

        exec_input = json.dumps(
            {
                "TableName": table_name,
                "Item": {"data": {"S": "HelloWorld"}, "id": {"S": "id1"}},
                "Key": {"id": {"S": "id1"}},
            }
        )
        create_and_record_execution(
            aws_client,
            create_state_machine_iam_role,
            create_state_machine,
            sfn_snapshot,
            definition,
            exec_input,
        )

    @markers.aws.needs_fixing
    def test_put_update_get_item(
        self,
        aws_client,
        create_state_machine_iam_role,
        create_state_machine,
        dynamodb_create_table,
        sfn_snapshot,
    ):
        sfn_snapshot.add_transformer(sfn_snapshot.transform.dynamodb_api())

        table_name = f"sfn_test_table_{short_uid()}"
        dynamodb_create_table(table_name=table_name, partition_key="id", client=aws_client.dynamodb)

        template = ST.load_sfn_template(ST.DYNAMODB_PUT_UPDATE_GET_ITEM)
        definition = json.dumps(template)

        exec_input = json.dumps(
            {
                "TableName": table_name,
                "Item": {"data": {"S": "HelloWorld"}, "id": {"S": "id1"}},
                "Key": {"id": {"S": "id1"}},
                "UpdateExpression": "set S=:r",
                "ExpressionAttributeValues": {":r": {"S": "HelloWorldUpdated"}},
            }
        )
        create_and_record_execution(
            aws_client,
            create_state_machine_iam_role,
            create_state_machine,
            sfn_snapshot,
            definition,
            exec_input,
        )
