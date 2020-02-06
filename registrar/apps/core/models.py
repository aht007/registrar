""" Core models. """

from django.contrib.auth.models import AbstractUser, Group
from django.db import models
from django.utils.translation import ugettext_lazy as _
from guardian.shortcuts import remove_perm
from model_utils.models import TimeStampedModel

from . import permissions as perms


ACCESS_ADMIN = ('admin', 2)
ACCESS_WRITE = ('write', 1)
ACCESS_READ = ('read', 0)


class User(AbstractUser):
    """
    Custom user model for use with OpenID Connect.

    .. pii:: Stores full name, username, and email address for a user
    .. pii_types:: name, other
    .. pii_retirement:: local_api
    """
    full_name = models.CharField(_('Full Name'), max_length=255, blank=True, null=True)

    @property
    def access_token(self):
        """
        Returns an OAuth2 access token for this user, if one exists; otherwise None.

        Assumes user has authenticated at least once with edX Open ID Connect.
        """
        try:
            return self.social_auth.first().extra_data[u'access_token']
        except Exception:  # pylint: disable=broad-except
            return None

    class Meta(object):
        get_latest_by = 'date_joined'

    def get_full_name(self):
        return self.full_name or super(User, self).get_full_name()

    def __str__(self):
        """
        Human-friendly string representation of this User.
        """
        return str(self.username)


class Organization(TimeStampedModel):
    """
    Model that represents a course-discovery Organization entity.

    .. no_pii::
    """
    class Meta(object):
        app_label = 'core'
        permissions = (
            (perms.ORGANIZATION_READ_METADATA_KEY, 'View Metadata'),
            (perms.ORGANIZATION_READ_ENROLLMENTS_KEY, 'Read enrollment data'),
            (perms.ORGANIZATION_WRITE_ENROLLMENTS_KEY, 'Write enrollment data'),
            (perms.ORGANIZATION_READ_REPORTS_KEY, 'Read reports data'),
        )
    key = models.CharField(unique=True, max_length=255)
    discovery_uuid = models.UUIDField(db_index=True, null=True)
    name = models.CharField(max_length=255)

    def __str__(self):
        """
        Human-friendly string representation of this Organization.
        """
        return self.name

    def __repr__(self):
        """
        Developer-friendly string representation of this Organization.
        """
        return "<{}: key={} discovery_uuid={} name={!r}>".format(
            type(self).__name__, self.key, self.discovery_uuid, self.name
        )


class Program(TimeStampedModel):
    """
    Table that referrences a course-discovery Program entity.

    .. no_pii::
    """
    class Meta(object):
        app_label = 'core'
        permissions = (
            (perms.PROGRAM_READ_METADATA_KEY, 'View program metadata'),
            (perms.PROGRAM_READ_ENROLLMENTS_KEY, 'Read program enrollment data'),
            (perms.PROGRAM_WRITE_ENROLLMENTS_KEY, 'Write program enrollment data'),
            (perms.PROGRAM_READ_REPORTS_KEY, 'Read program reports data'),
        )
    key = models.CharField(unique=True, max_length=255)
    discovery_uuid = models.UUIDField(db_index=True, null=True)
    managing_organization = models.ForeignKey(Organization, on_delete=models.CASCADE)

    def __str__(self):
        """
        Human-friendly string representation of this Program.
        """
        return self.key

    def __repr__(self):
        """
        Developer-friendly string representation of this Program.
        """
        return "<{}: key={} discovery_uuid={} managing_organization={}>".format(
            type(self).__name__, self.key, self.discovery_uuid, self.managing_organization.key
        )


class OrganizationGroup(Group):
    """
    Group subclass to grant select guardian permissions to a group on an organization level.

    .. no_pii::
    """
    objects = models.Manager()

    class Meta(object):
        app_label = 'core'
        verbose_name = 'Organization Group'

    ROLE_CHOICES = (
        (role.name, role.description)
        for role in perms.ORGANIZATION_ROLES
    )

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    role = models.CharField(
        max_length=255,
        choices=ROLE_CHOICES,
        default=perms.OrganizationReadMetadataRole.name,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Save the value of organization in an attribute, so that when
        # save() is called, we have access to the old value.
        try:
            self._initial_organization = self.organization
        except Organization.DoesNotExist:   # pragma: no cover
            self._initial_organization = None

    @property
    def role_object(self):
        """
        Converts self.role (which is a role name) to its matching Role instance.
        """
        for role in perms.ORGANIZATION_ROLES:
            if self.role == role.name:
                return role
        return None  # pragma: no cover

    # pylint: disable=arguments-differ
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self._initial_organization:  # pragma: no branch
            for perm in perms.ORGANIZATION_PERMISSIONS:
                remove_perm(perm, self, self._initial_organization)
        self.role_object.assign_to_group(self, self.organization)
        self._initial_organization = self.organization

    def __str__(self):
        """
        Human-friendly representation of this OrganizationGroup.
        """
        return self.name

    def __repr__(self):
        """
        Developer-friendly representation of this OrganizationGroup.
        """
        return '<{}: name={!r} organization={} role={}>'.format(
            type(self).__name__, self.name, self.organization.key, self.role
        )


class ProgramOrganizationGroup(Group):
    """
    Group subclass to grant select guardian permissions to a group on a program level.

    .. no_pii::
    """

    objects = models.Manager()

    class Meta(object):
        app_label = 'core'
        verbose_name = 'Program Group'

    ROLE_CHOICES = (
        (role.name, role.description)
        for role in perms.PROGRAM_ROLES
    )

    program = models.ForeignKey(Program, on_delete=models.CASCADE)
    granting_organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    role = models.CharField(
        max_length=255,
        choices=ROLE_CHOICES,
        default=perms.ProgramReadMetadataRole.name,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self._initial_program = self.program
        except Program.DoesNotExist:   # pragma: no cover
            self._initial_program = None

    @property
    def role_object(self):
        """
        Converts self.role (which is a role name) to its matching Role instance.
        """
        for role in perms.PROGRAM_ROLES:
            if self.role == role.name:  # pragma: no branch
                return role
        return None  # pragma: no cover

    # pylint: disable=arguments-differ
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self._initial_program:  # pragma: no branch
            for perm in perms.PROGRAM_PERMISSIONS:
                remove_perm(perm, self, self._initial_program)
        self.role_object.assign_to_group(self, self.program)
        self._initial_program = self.program

    def __str__(self):
        """
        Human-friendly representation of this ProgramOrganizationGroup.
        """
        return self.name

    def __repr__(self):
        """
        Developer-friendly representation of this ProgramOrganizationGroup.
        """
        return (
            "<{}: name={!r} program={} granting_organization={} role={}>".format(
                type(self).__name__,
                self.name,
                self.program.key,
                self.granting_organization.key,
                self.role,
            )
        )


class PendingUserGroup(TimeStampedModel):
    """
    Membership model for user who have not yet been created in the user table

    .. pii:: stores the user email address field for pending users.
             The pii data gets deleted after a real user gets created
    .. pii_types:: email_address
    .. pii_retirement:: local_api
    """
    class Meta(object):
        ordering = ['created']
        unique_together = ('user_email', 'group')

    user_email = models.EmailField()
    group = models.ForeignKey(Group, on_delete=models.CASCADE)

    def __repr__(self):
        """
        Return human-readable string representation of this PendingUserGroup.
        """
        return "<{}: user_email={!r} group={!r}>".format(
            type(self).__name__, self.user_email, self.group
        )

    def __str__(self):
        """
        Return human-readable string representation of this PendingUserGroup.
        """
        return "pending membership of {} in {}".format(self.user_email, self.group)


class JobPermissionSupport(models.Model):
    """
    'Model' allowing us to define permissions related to jobs, which do not
    have a model associated with them (they are simply an abstraction around
    UserTasks).

    We set Meta.managed to False so that a database table is not created.

    .. no_pii::
    """

    class Meta:
        managed = False  # Do not create a database table
        permissions = (
            (perms.JOB_GLOBAL_READ_KEY, 'Global Job status reading'),
        )
