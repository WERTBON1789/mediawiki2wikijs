#!/usr/bin/env python3
from gql import Client
from gql.dsl import DSLMutation, DSLSchema, DSLVariableDefinitions, DSLQuery, dsl_gql
from gql.transport.requests import RequestsHTTPTransport
from uuid import uuid4
from constants import *

__client = Client(
    transport=RequestsHTTPTransport(
        url=WIKIJS_HOST + "/graphql",
        headers={"Authorization": "Bearer " + WIKIJS_TOKEN},
    ),
    fetch_schema_from_transport=True,
)
s = __client.connect_sync()
schema = DSLSchema(__client.schema)

__var = DSLVariableDefinitions()
create_user = DSLMutation(
    schema.Mutation.users.select(
        schema.UserMutation.create(
            email=__var.email,
            name=__var.name,
            passwordRaw=__var.password.default(str(uuid4())),
            providerKey=__var.providerKey.default("local"),
            groups=[],
        ).select(
            schema.UserResponse.responseResult.select(schema.ResponseStatus.errorCode)
        )
    )
)
create_user.variable_definitions = __var
create_user = dsl_gql(create_user)

__var = DSLVariableDefinitions()
delete_page = DSLMutation(
    schema.Mutation.pages.select(
        schema.PageMutation.delete(id=__var.id).select(
            schema.DefaultResponse.responseResult.select(
                schema.ResponseStatus.errorCode
            )
        )
    )
)
delete_page.variable_definitions = __var
delete_page = dsl_gql(delete_page)

__var = DSLVariableDefinitions()
update_page = DSLMutation(
    schema.Mutation.pages.select(
        schema.PageMutation.update(
            id=__var.id,
            content=__var.content,
            isPublished=True,
            isPrivate=False,
        ).select(
            schema.PageResponse.responseResult.select(schema.ResponseStatus.errorCode)
        )
    )
)
update_page.variable_definitions = __var
update_page = dsl_gql(update_page)

__var = DSLVariableDefinitions()
create_page = DSLMutation(
    schema.Mutation.pages.select(
        schema.PageMutation.create(
            content=__var.content,
            editor="markdown",
            isPrivate=False,
            isPublished=True,
            locale=LOCALE,
            path=__var.path,
            tags=[],
            title=__var.title,
            description="",
            scriptJs=__var.scriptJs.default(None)
        ).select(
            schema.PageResponse.responseResult.select(schema.ResponseStatus.slug),
            schema.PageResponse.page.select(schema.Page.id),
        )
    )
)
create_page.variable_definitions = __var
create_page = dsl_gql(create_page)

__var = DSLVariableDefinitions()
search_page = DSLQuery(
    schema.Query.pages.select(
        schema.PageQuery.search(query=__var.path).select(
            schema.PageSearchResponse.results.select(
                schema.PageSearchResult.id, schema.PageSearchResult.path
            )
        )
    )
)
search_page.variable_definitions = __var
search_page = dsl_gql(search_page)

