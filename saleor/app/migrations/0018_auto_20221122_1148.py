
# Generated by Django 3.2.16 on 2022-11-22 11:48

from django.db import migrations, models

# Forward helpers
DROP_OLD_CONSTRAINTS = """
ALTER TABLE app_app_permissions
    DROP CONSTRAINT IF EXISTS account_serviceaccou_permission_id_449791f0_fk_auth_perm;
ALTER TABLE app_app_permissions
    DROP CONSTRAINT IF EXISTS app_app_permissions_permission_id_defe4a88_fk_auth_perm;

ALTER TABLE app_appextension_permissions
    DROP CONSTRAINT app_appextension_per_permission_id_cb6c3ce0_fk_auth_perm;

ALTER TABLE app_appinstallation_permissions
    DROP CONSTRAINT app_appinstallation__permission_id_4ee9f6c8_fk_auth_perm;
"""

CREATE_NEW_CONSTRAINTS = """
ALTER TABLE app_app_permissions
    ADD CONSTRAINT app_app_permissions_permission_id_defe4a88_fk_permissio
    FOREIGN KEY (permission_id) REFERENCES permission_permission (id)
    DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE app_appextension_permissions
    ADD CONSTRAINT app_appextension_per_permission_id_cb6c3ce0_fk_permissio
    FOREIGN KEY (permission_id) REFERENCES permission_permission (id)
    DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE app_appinstallation_permissions
    ADD CONSTRAINT app_appinstallation__permission_id_4ee9f6c8_fk_permissio
    FOREIGN KEY (permission_id) REFERENCES permission_permission (id)
    DEFERRABLE INITIALLY DEFERRED;
"""

# Reverse helpers
CREATE_NEW_CONSTRAINTS_REVERSE = """
ALTER TABLE app_app_permissions
    DROP CONSTRAINT app_app_permissions_permission_id_defe4a88_fk_permissio;

ALTER TABLE app_appextension_permissions
    DROP CONSTRAINT app_appextension_per_permission_id_cb6c3ce0_fk_permissio;

ALTER TABLE app_appinstallation_permissions
    DROP CONSTRAINT app_appinstallation__permission_id_4ee9f6c8_fk_permissio;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("permission", "0001_initial"),
        ("app", "0017_app_audience"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                # Those constraints should be reverted after rename table in
                # account 0072 migration.
                migrations.RunSQL(
                    DROP_OLD_CONSTRAINTS, reverse_sql=migrations.RunSQL.noop
                ),
                migrations.RunSQL(
                    CREATE_NEW_CONSTRAINTS, reverse_sql=CREATE_NEW_CONSTRAINTS_REVERSE
                ),
            ],
            state_operations=[
                migrations.AlterField(
                    model_name="app",
                    name="permissions",
                    field=models.ManyToManyField(
                        blank=True,
                        help_text="Specific permissions for this app.",
                        related_name="app_set",
                        related_query_name="app",
                        to="permission.Permission",
                    ),
                ),
                migrations.AlterField(
                    model_name="appextension",
                    name="permissions",
                    field=models.ManyToManyField(
                        blank=True,
                        help_text="Specific permissions for this app extension.",
                        to="permission.Permission",
                    ),
                ),
                migrations.AlterField(
                    model_name="appinstallation",
                    name="permissions",
                    field=models.ManyToManyField(
                        blank=True,
                        help_text="Specific permissions which will be assigned to app.",
                        related_name="app_installation_set",
                        related_query_name="app_installation",
                        to="permission.Permission",
                    ),
                ),
            ],
        )
    ]