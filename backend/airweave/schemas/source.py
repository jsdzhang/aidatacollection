"""Source schema.

Sources represent the available data connector types that Airweave can use to sync data
from external systems. Each source defines the authentication and configuration requirements
for connecting to a specific type of data source.
"""

from datetime import datetime
from typing import Any, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_serializer, field_validator

from airweave.platform.auth.schemas import AuthType
from airweave.platform.configs._base import Fields


class SourceBase(BaseModel):
    """Base schema for Source with common fields."""

    name: str = Field(
        ...,
        description=(
            "Human-readable name of the data source connector (e.g., 'GitHub', 'Stripe', "
            "'PostgreSQL')."
        ),
    )
    description: Optional[str] = Field(
        None,
        description=(
            "Detailed description explaining what data this source can extract and its "
            "typical use cases."
        ),
    )
    auth_type: Optional[AuthType] = Field(
        None,
        description="Type of authentication mechanism required by this source (e.g., 'oauth2').",
    )
    auth_config_class: str = Field(
        ...,
        description=(
            "Python class name that defines the authentication configuration fields "
            "required for this source."
        ),
    )
    config_class: str = Field(
        ...,
        description=(
            "Python class name that defines the source-specific configuration options "
            "and parameters."
        ),
    )
    short_name: str = Field(
        ...,
        description=(
            "Technical identifier used internally to reference this source type. Must be unique "
            "across all sources."
        ),
    )
    class_name: str = Field(
        ...,
        description=(
            "Python class name of the source implementation that handles data extraction logic."
        ),
    )
    output_entity_definition_ids: Optional[List[UUID]] = Field(
        None,
        description=(
            "List of entity definition IDs that this source can produce. Defines the data schema "
            "and structure that this connector outputs."
        ),
    )
    organization_id: Optional[UUID] = Field(
        None,
        description=(
            "Organization identifier for custom source connectors. System sources have this "
            "set to null."
        ),
    )
    labels: Optional[List[str]] = Field(
        None,
        description=(
            "Categorization tags to help users discover and filter sources by domain or use case."
        ),
    )

    @field_serializer("output_entity_definition_ids")
    def serialize_output_entity_definition_ids(
        self, output_entity_definition_ids: Optional[List[UUID]]
    ) -> Optional[List[str]]:
        """Convert UUID list to string list during serialization."""
        if output_entity_definition_ids is None:
            return None
        return [str(uuid) for uuid in output_entity_definition_ids]

    @field_validator("output_entity_definition_ids", mode="before")
    @classmethod
    def validate_output_entity_definition_ids(cls, value: Any) -> Optional[List[UUID]]:
        """Convert string list to UUID list during deserialization."""
        if value is None:
            return None
        if isinstance(value, list):
            return [UUID(str(item)) if not isinstance(item, UUID) else item for item in value]
        return value

    class Config:
        """Pydantic config for SourceBase."""

        from_attributes = True


class SourceCreate(SourceBase):
    """Schema for creating a Source object."""

    pass


class SourceUpdate(SourceBase):
    """Schema for updating a Source object."""

    pass


class SourceInDBBase(SourceBase):
    """Base schema for Source stored in database with system fields."""

    id: UUID = Field(
        ...,
        description=(
            "Unique system identifier for this source type. Generated automatically when the "
            "source is registered."
        ),
    )
    created_at: datetime = Field(
        ...,
        description=(
            "Timestamp when this source type was registered in the system (ISO 8601 format)."
        ),
    )
    modified_at: datetime = Field(
        ...,
        description="Timestamp when this source type was last updated (ISO 8601 format).",
    )

    class Config:
        """Pydantic config for SourceInDBBase."""

        from_attributes = True


class Source(SourceInDBBase):
    """Complete source representation with authentication and configuration schemas."""

    auth_fields: Fields = Field(
        ...,
        description=(
            "Schema definition for authentication fields required to connect to this source. "
            "Describes field types, validation rules, and user interface hints."
        ),
    )
    config_fields: Fields = Field(
        ...,
        description=(
            "Schema definition for configuration fields required to customize this source. "
            "Describes field types, validation rules, and user interface hints."
        ),
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "name": "GitHub",
                    "description": (
                        "Connect to GitHub repositories for code, issues, pull requests, "
                        "and documentation"
                    ),
                    "auth_type": "config_class",
                    "auth_config_class": "GitHubAuthConfig",
                    "config_class": "GitHubConfig",
                    "short_name": "github",
                    "class_name": "GitHubSource",
                    "output_entity_definition_ids": [
                        "def12345-6789-abcd-ef01-234567890abc",
                        "def67890-abcd-ef01-2345-67890abcdef1",
                    ],
                    "organization_id": None,
                    "labels": ["code"],
                    "created_at": "2024-01-01T00:00:00Z",
                    "modified_at": "2024-01-01T00:00:00Z",
                    "auth_fields": {
                        "fields": [
                            {
                                "name": "personal_access_token",
                                "title": "Personal Access Token",
                                "description": (
                                    "Personal Access Token with repository read permissions. "
                                    "Generate one at https://github.com/settings/tokens"
                                ),
                                "type": "string",
                                "secret": True,
                            },
                            {
                                "name": "repo_name",
                                "title": "Repository Name",
                                "description": (
                                    "Full repository name in format 'owner/repo' "
                                    "(e.g., 'airweave-ai/airweave')"
                                ),
                                "type": "string",
                            },
                        ]
                    },
                    "config_fields": {
                        "fields": [
                            {
                                "name": "branch",
                                "title": "Branch name",
                                "description": (
                                    "Specific branch to sync (e.g., 'main', 'development'). "
                                    "If empty, uses the default branch."
                                ),
                                "type": "string",
                            },
                        ]
                    },
                }
            ]
        }
    }
