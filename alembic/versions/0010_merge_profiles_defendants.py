"""Join independent profile and precedent migrations without changing existing data.

Both parent upgrades are additive for private case/account records. Backfill is unchanged.
Rollback: keep this marker and user_profiles when reverting the application; dropping
profiles requires exporting them first. No data is altered by this merge revision.
"""

revision = "0010_merge_profiles_defendants"
down_revision = ("0009_user_profiles", "0009_precedent_defendants")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
