from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('market', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='SiteConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('finnhub_api_key', models.CharField(blank=True, default='', max_length=128)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
    ]

