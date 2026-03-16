"""初始建表迁移：users / behavior_events / risk_scores / alerts / ml_models

Revision ID: 001_initial
Revises:
Create Date: 2026-03-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # users
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("username", sa.String(100), nullable=False, unique=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("phone", sa.String(20), nullable=True, unique=True),
        sa.Column("hashed_password", sa.Text, nullable=False),
        sa.Column("fcm_token", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("is_admin", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("home_country", sa.String(3), nullable=True),
        sa.Column("home_city", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_users_username", "users", ["username"])
    op.create_index("ix_users_email", "users", ["email"])

    # behavior_events（分区表由 DBA/脚本创建，此处建主表）
    op.create_table(
        "behavior_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("action_type", sa.String(100), nullable=True),
        sa.Column("ip_address", postgresql.INET, nullable=True),
        sa.Column("user_agent", sa.Text, nullable=True),
        sa.Column("device_fingerprint_hash", sa.String(64), nullable=True),
        sa.Column("is_new_device", sa.Boolean, nullable=True),
        sa.Column("geo_country", sa.String(3), nullable=True),
        sa.Column("geo_city", sa.String(100), nullable=True),
        sa.Column("geo_lat", sa.Float, nullable=True),
        sa.Column("geo_lng", sa.Float, nullable=True),
        sa.Column("geo_isp", sa.String(200), nullable=True),
        sa.Column("is_vpn", sa.Boolean, nullable=True),
        sa.Column("distance_from_home_km", sa.Float, nullable=True),
        sa.Column("action_data", postgresql.JSONB, nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("risk_score", sa.SmallInteger, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_behavior_events_user_id", "behavior_events", ["user_id"])
    op.create_index("ix_behavior_events_created_at", "behavior_events", ["created_at"])
    op.create_index("ix_behavior_events_user_created", "behavior_events", ["user_id", "created_at"])

    # risk_scores
    op.create_table(
        "risk_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("score", sa.SmallInteger, nullable=False),
        sa.Column("level", sa.String(10), nullable=False),
        sa.Column("lstm_score", sa.Float, nullable=True),
        sa.Column("rule_score", sa.Float, nullable=True),
        sa.Column("velocity_score", sa.Float, nullable=True),
        sa.Column("triggered_rules", postgresql.ARRAY(sa.Text), nullable=True),
        sa.Column("model_version", sa.String(20), nullable=True),
        sa.Column("components", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_risk_scores_user_id", "risk_scores", ["user_id"])
    op.create_index("ix_risk_scores_created_at", "risk_scores", ["created_at"])

    # alerts
    op.create_table(
        "alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("risk_score_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("risk_scores.id", ondelete="SET NULL"), nullable=True),
        sa.Column("channels", postgresql.ARRAY(sa.Text), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_alerts_user_id", "alerts", ["user_id"])
    op.create_index("ix_alerts_created_at", "alerts", ["created_at"])

    # ml_models
    op.create_table(
        "ml_models",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("version", sa.String(20), nullable=False, unique=True),
        sa.Column("model_type", sa.String(50), nullable=False, server_default="LSTM"),
        sa.Column("file_path", sa.Text, nullable=False),
        sa.Column("train_samples", sa.Integer, nullable=True),
        sa.Column("val_loss", sa.Float, nullable=True),
        sa.Column("auc_roc", sa.Float, nullable=True),
        sa.Column("precision", sa.Float, nullable=True),
        sa.Column("recall", sa.Float, nullable=True),
        sa.Column("f1_score", sa.Float, nullable=True),
        sa.Column("hyperparams", postgresql.JSONB, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("trained_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("ml_models")
    op.drop_table("alerts")
    op.drop_table("risk_scores")
    op.drop_table("behavior_events")
    op.drop_table("users")
