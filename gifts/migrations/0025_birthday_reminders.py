from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("gifts", "0024_subscription_delivery_preferences")]
    operations = [
        migrations.AddField(model_name="user", name="birthday", field=models.DateField(blank=True, null=True)),
        migrations.AddField(model_name="subscription", name="birthday_reminder", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="subscription", name="christmas_reminder", field=models.BooleanField(default=False)),
        migrations.CreateModel(name="ReminderDelivery", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("event", models.CharField(choices=[("birthday", "Birthday"), ("christmas", "Christmas")], max_length=10)),
            ("event_year", models.PositiveSmallIntegerField()),
            ("sent_at", models.DateTimeField(auto_now_add=True)),
            ("subscription", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="reminder_deliveries", to="gifts.subscription")),
        ]),
        migrations.AddConstraint(model_name="reminderdelivery", constraint=models.UniqueConstraint(fields=("subscription", "event", "event_year"), name="unique_subscription_event_reminder")),
    ]
