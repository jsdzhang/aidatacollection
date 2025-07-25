"""API endpoints for organizations."""

from typing import List
from uuid import UUID

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from airweave import crud, schemas
from airweave.api import deps
from airweave.api.router import TrailingSlashRouter
from airweave.core.datetime_utils import utc_now_naive
from airweave.core.logging import logger
from airweave.core.organization_service import organization_service
from airweave.models.user import User
from airweave.schemas.auth import AuthContext

router = TrailingSlashRouter()


@router.post("/", response_model=schemas.Organization)
async def create_organization(
    organization_data: schemas.OrganizationCreate,
    db: AsyncSession = Depends(deps.get_db),
    user: User = Depends(deps.get_user),
) -> schemas.Organization:
    """Create a new organization with current user as owner.

    Integrates with Auth0 Organizations API when available for enhanced multi-org support.

    Args:
        organization_data: The organization data to create
        db: Database session
        user: The current authenticated user

    Returns:
        The created organization with user's role

    Raises:
        HTTPException: If organization name already exists or creation fails
    """
    # Create the organization with Auth0 integration
    try:
        organization = await organization_service.create_organization_with_auth0(
            db=db, org_data=organization_data, owner_user=user
        )

        return organization
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to create organization: {str(e)}"
        ) from e


@router.get("/", response_model=List[schemas.OrganizationWithRole])
async def list_user_organizations(
    db: AsyncSession = Depends(deps.get_db),
    user: User = Depends(deps.get_user),
) -> List[schemas.OrganizationWithRole]:
    """Get all organizations the current user belongs to.

    Args:
        db: Database session
        user: The current authenticated user

    Returns:
        List of organizations with user's role in each
    """
    organizations = await crud.organization.get_user_organizations_with_roles(
        db=db, user_id=user.id
    )

    return [
        schemas.OrganizationWithRole(
            id=org.id,
            name=org.name,
            description=org.description or "",
            created_at=org.created_at,
            modified_at=org.modified_at,
            role=org.role,
            is_primary=org.is_primary,
        )
        for org in organizations
    ]


@router.get("/{organization_id}", response_model=schemas.OrganizationWithRole)
async def get_organization(
    organization_id: UUID,
    db: AsyncSession = Depends(deps.get_db),
    auth_context: AuthContext = Depends(deps.get_auth_context),
) -> schemas.OrganizationWithRole:
    """Get a specific organization by ID.

    Args:
        organization_id: The ID of the organization to get
        db: Database session
        auth_context: The current authenticated user

    Returns:
        The organization with user's role

    Raises:
        HTTPException: If organization not found or user doesn't have access
    """
    # Validate access and get user's membership (this now has security built-in)
    user_org = await crud.organization.get_user_membership(
        db=db,
        organization_id=organization_id,
        user_id=auth_context.user.id,
        auth_context=auth_context,
    )

    if not user_org:
        raise HTTPException(
            status_code=404, detail="Organization not found or you don't have access to it"
        )

    # Capture the role and is_primary values early to avoid greenlet exceptions later
    user_role = user_org.role
    user_is_primary = user_org.is_primary

    organization = await crud.organization.get(db=db, id=organization_id, auth_context=auth_context)

    return schemas.OrganizationWithRole(
        id=organization.id,
        name=organization.name,
        description=organization.description or "",
        created_at=organization.created_at,
        modified_at=organization.modified_at,
        role=user_role,
        is_primary=user_is_primary,
    )


@router.put("/{organization_id}", response_model=schemas.OrganizationWithRole)
async def update_organization(
    organization_id: UUID,
    organization_data: schemas.OrganizationCreate,  # Reuse the same schema
    db: AsyncSession = Depends(deps.get_db),
    auth_context: AuthContext = Depends(deps.get_auth_context),
) -> schemas.OrganizationWithRole:
    """Update an organization.

    Only organization owners and admins can update organizations.

    Args:
        organization_id: The ID of the organization to update
        organization_data: The updated organization data
        db: Database session
        auth_context: The current authenticated user

    Returns:
        The updated organization with user's role

    Raises:
        HTTPException: If organization not found, user doesn't have permission,
                      or organization name conflicts
    """
    # Get user's membership and validate admin access
    user_org = await crud.organization.get_user_membership(
        db=db,
        organization_id=organization_id,
        user_id=auth_context.user.id,
        auth_context=auth_context,
    )

    if not user_org:
        raise HTTPException(
            status_code=404, detail="Organization not found or you don't have access to it"
        )

    # Capture the role and is_primary values early to avoid greenlet exceptions later
    user_role = user_org.role
    user_is_primary = user_org.is_primary

    if user_role not in ["owner", "admin"]:
        raise HTTPException(
            status_code=403, detail="Only organization owners and admins can update organizations"
        )

    # Check if the new name conflicts with existing organizations (if name is being changed)
    organization = await crud.organization.get(db=db, id=organization_id, auth_context=auth_context)

    update_data = schemas.OrganizationUpdate(
        name=organization_data.name, description=organization_data.description or ""
    )

    updated_organization = await crud.organization.update(
        db=db, db_obj=organization, obj_in=update_data, auth_context=auth_context
    )

    return schemas.OrganizationWithRole(
        id=updated_organization.id,
        name=updated_organization.name,
        description=updated_organization.description or "",
        created_at=updated_organization.created_at,
        modified_at=updated_organization.modified_at,
        role=user_role,
        is_primary=user_is_primary,
    )


@router.delete("/{organization_id}", response_model=schemas.OrganizationWithRole)
async def delete_organization(
    organization_id: UUID,
    db: AsyncSession = Depends(deps.get_db),
    auth_context: AuthContext = Depends(deps.get_auth_context),
) -> schemas.OrganizationWithRole:
    """Delete an organization.

    Only organization owners can delete organizations.

    Args:
        organization_id: The ID of the organization to delete
        db: Database session
        auth_context: The current authenticated user

    Returns:
        The deleted organization

    Raises:
        HTTPException: If organization not found, user doesn't have permission,
                      or organization cannot be deleted
    """
    # Get user's membership (this now validates access automatically)
    user_org = await crud.organization.get_user_membership(
        db=db,
        organization_id=organization_id,
        user_id=auth_context.user.id,
        auth_context=auth_context,
    )

    if not user_org:
        raise HTTPException(
            status_code=404, detail="Organization not found or you don't have access to it"
        )

    # Capture the role and is_primary values early to avoid greenlet exceptions later
    user_role = user_org.role
    user_is_primary = user_org.is_primary

    if user_role != "owner":
        raise HTTPException(
            status_code=403, detail="Only organization owners can delete organizations"
        )

    # Check if this is the user's only organization
    user_orgs = await crud.organization.get_user_organizations_with_roles(
        db=db, user_id=auth_context.user.id
    )

    if len(user_orgs) <= 1:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete your only organization. Contact support to delete your account.",
        )

    # Delete the organization using Auth0 service (handles both local and Auth0 deletion)
    try:
        success = await organization_service.delete_organization_with_auth0(
            db=db,
            organization_id=organization_id,
            deleting_user=auth_context.user,
        )

        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete organization")

        # Return the deleted organization info
        # Note: We use the captured values since the org is now deleted
        return schemas.OrganizationWithRole(
            id=organization_id,
            name="",  # Organization name is no longer available after deletion
            description="",
            created_at=utc_now_naive(),  # Placeholder values
            modified_at=utc_now_naive(),
            role=user_role,
            is_primary=user_is_primary,
        )

    except Exception as e:
        logger.error(f"Failed to delete organization {organization_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to delete organization: {str(e)}"
        ) from e


@router.post("/{organization_id}/set-primary", response_model=schemas.OrganizationWithRole)
async def set_primary_organization(
    organization_id: UUID,
    db: AsyncSession = Depends(deps.get_db),
    auth_context: AuthContext = Depends(deps.get_auth_context),
) -> schemas.OrganizationWithRole:
    """Set an organization as the user's primary organization.

    Args:
        organization_id: The ID of the organization to set as primary
        db: Database session
        auth_context: The current authenticated user

    Returns:
        The organization with updated primary status

    Raises:
        HTTPException: If organization not found or user doesn't have access
    """
    # Set as primary organization
    success = await crud.organization.set_primary_organization(
        db=db,
        user_id=auth_context.user.id,
        organization_id=organization_id,
        auth_context=auth_context,
    )

    if not success:
        raise HTTPException(
            status_code=404, detail="Organization not found or you don't have access to it"
        )

    # Get the updated organization data
    user_org = await crud.organization.get_user_membership(
        db=db,
        organization_id=organization_id,
        user_id=auth_context.user.id,
        auth_context=auth_context,
    )

    organization = await crud.organization.get(db=db, id=organization_id, auth_context=auth_context)

    if not organization or not user_org:
        raise HTTPException(status_code=404, detail="Organization not found")

    return schemas.OrganizationWithRole(
        id=organization.id,
        name=organization.name,
        description=organization.description or "",
        created_at=organization.created_at,
        modified_at=organization.modified_at,
        role=user_org.role,
        is_primary=user_org.is_primary,
    )


# Member Management Endpoints


@router.post("/{organization_id}/invite", response_model=schemas.InvitationResponse)
async def invite_user_to_organization(
    organization_id: UUID,
    invitation_data: schemas.InvitationCreate,
    db: AsyncSession = Depends(deps.get_db),
    auth_context: AuthContext = Depends(deps.get_auth_context),
) -> schemas.InvitationResponse:
    """Send organization invitation via Auth0."""
    # Validate user has admin access using auth context
    user_org = None
    for org in auth_context.user.user_organizations:
        if org.organization.id == organization_id:
            user_org = org
            break

    if not user_org or user_org.role not in ["owner", "admin"]:
        raise HTTPException(
            status_code=403, detail="Only organization owners and admins can invite members"
        )

    try:
        invitation = await organization_service.invite_user_to_organization(
            db=db,
            organization_id=organization_id,
            email=invitation_data.email,
            role=invitation_data.role,
            inviter_user=auth_context.user,
        )

        return schemas.InvitationResponse(
            id=invitation["id"],
            email=invitation_data.email,
            role=invitation_data.role,
            status="pending",
            invited_at=invitation.get("created_at"),
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/{organization_id}/invitations", response_model=List[schemas.InvitationResponse])
async def get_pending_invitations(
    organization_id: UUID,
    db: AsyncSession = Depends(deps.get_db),
    auth_context: AuthContext = Depends(deps.get_auth_context),
) -> List[schemas.InvitationResponse]:
    """Get pending invitations for organization."""
    # Validate user has access to organization using auth context
    user_org = None
    for org in auth_context.user.user_organizations:
        if org.organization.id == organization_id:
            user_org = org
            break

    if not user_org:
        raise HTTPException(
            status_code=404, detail="Organization not found or you don't have access to it"
        )

    try:
        invitations = await organization_service.get_pending_invitations(
            db=db,
            organization_id=organization_id,
            requesting_user=auth_context.user,
        )

        return [
            schemas.InvitationResponse(
                id=inv["id"],
                email=inv["email"],
                role=inv["role"],
                status=inv["status"],
                invited_at=inv["invited_at"],
            )
            for inv in invitations
        ]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete("/{organization_id}/invitations/{invitation_id}", response_model=dict)
async def remove_pending_invitation(
    organization_id: UUID,
    invitation_id: str,
    db: AsyncSession = Depends(deps.get_db),
    auth_context: AuthContext = Depends(deps.get_auth_context),
) -> dict:
    """Remove a pending invitation."""
    # Validate user has admin access using auth context
    user_org = None
    for org in auth_context.user.user_organizations:
        if org.organization.id == organization_id:
            user_org = org
            break

    if not user_org or user_org.role not in ["owner", "admin"]:
        raise HTTPException(
            status_code=403, detail="Only organization owners and admins can remove invitations"
        )

    try:
        success = await organization_service.remove_pending_invitation(
            db=db,
            organization_id=organization_id,
            invitation_id=invitation_id,
            remover_user=auth_context.user,
        )

        if success:
            return {"message": "Invitation removed successfully"}
        else:
            raise HTTPException(status_code=404, detail="Invitation not found")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/{organization_id}/members", response_model=List[schemas.MemberResponse])
async def get_organization_members(
    organization_id: UUID,
    db: AsyncSession = Depends(deps.get_db),
    auth_context: AuthContext = Depends(deps.get_auth_context),
) -> List[schemas.MemberResponse]:
    """Get all members of an organization."""
    # Validate user has access to organization using auth context
    user_org = None
    for org in auth_context.user.user_organizations:
        if org.organization.id == organization_id:
            user_org = org
            break

    if not user_org:
        raise HTTPException(
            status_code=404, detail="Organization not found or you don't have access to it"
        )

    try:
        members = await organization_service.get_organization_members(
            db=db,
            organization_id=organization_id,
            requesting_user=auth_context.user,
        )

        return [
            schemas.MemberResponse(
                id=member["id"],
                email=member["email"],
                name=member["name"],
                role=member["role"],
                status=member["status"],
                is_primary=member["is_primary"],
                auth0_id=member["auth0_id"],
            )
            for member in members
        ]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete("/{organization_id}/members/{user_id}", response_model=dict)
async def remove_member_from_organization(
    organization_id: UUID,
    user_id: UUID,
    db: AsyncSession = Depends(deps.get_db),
    auth_context: AuthContext = Depends(deps.get_auth_context),
) -> dict:
    """Remove a member from organization."""
    # Validate user has admin access using auth context
    user_org = None
    for org in auth_context.user.user_organizations:
        if org.organization.id == organization_id:
            user_org = org
            break

    if not user_org or user_org.role not in ["owner", "admin"]:
        raise HTTPException(
            status_code=403, detail="Only organization owners and admins can remove members"
        )

    # Don't allow removing yourself this way - use leave endpoint instead
    if user_id == auth_context.user.id:
        raise HTTPException(
            status_code=400, detail="Use the leave organization endpoint to remove yourself"
        )

    try:
        success = await organization_service.remove_member_from_organization(
            db=db,
            organization_id=organization_id,
            user_id=user_id,
            remover_user=auth_context.user,
        )

        if success:
            return {"message": "Member removed successfully"}
        else:
            raise HTTPException(status_code=404, detail="Member not found")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{organization_id}/leave", response_model=dict)
async def leave_organization(
    organization_id: UUID,
    db: AsyncSession = Depends(deps.get_db),
    auth_context: AuthContext = Depends(deps.get_auth_context),
) -> dict:
    """Leave an organization."""
    # Validate user is a member using auth context
    user_org = None
    for org in auth_context.user.user_organizations:
        if org.organization.id == organization_id:
            user_org = org
            break

    if not user_org:
        raise HTTPException(status_code=404, detail="You are not a member of this organization")

    # Check if this is the user's only organization
    user_orgs = await crud.organization.get_user_organizations_with_roles(
        db=db, user_id=auth_context.user.id
    )

    if len(user_orgs) <= 1:
        raise HTTPException(
            status_code=400,
            detail="Cannot leave your only organization. "
            "Users must belong to at least one organization. Delete the organization instead.",
        )

    # If user is an owner, check if there are other owners
    user_role = user_org.role
    if user_role == "owner":
        other_owners = await crud.organization.get_organization_owners(
            db=db,
            organization_id=organization_id,
            auth_context=auth_context,
            exclude_user_id=auth_context.user.id,
        )

        if not other_owners:
            raise HTTPException(
                status_code=400,
                detail="Cannot leave organization as the only owner. "
                "Transfer ownership to another member first.",
            )

    try:
        # Use the organization_service to handle leaving (which handles both local and Auth0)
        success = await organization_service.handle_user_leaving_organization(
            db=db,
            organization_id=organization_id,
            leaving_user=auth_context.user,
        )

        if success:
            return {"message": "Successfully left the organization"}
        else:
            raise HTTPException(status_code=500, detail="Failed to leave organization")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
