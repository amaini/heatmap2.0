from django.db import migrations, models
import django.db.models.deletion
import django.core.validators


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='Sector',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={'ordering': ['name']},
        ),
        migrations.CreateModel(
            name='Ticker',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('symbol', models.CharField(max_length=10, unique=True, validators=[django.core.validators.RegexValidator(message="Ticker symbol must be 1-10 chars, A-Z, digits, '.' or '-'", regex='^[A-Z][A-Z0-9\\.\\-]{0,9}$')])),
                ('company_name', models.CharField(blank=True, max_length=200)),
                ('security_type', models.CharField(default='Common Stock', help_text='Type of security, e.g., Common Stock', max_length=50)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('sector', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='tickers', to='market.sector')),
            ],
            options={'ordering': ['symbol']},
        ),
        migrations.CreateModel(
            name='PurchaseLot',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantity', models.DecimalField(decimal_places=4, max_digits=20, validators=[django.core.validators.MinValueValidator(0)])),
                ('price', models.DecimalField(decimal_places=4, max_digits=20, validators=[django.core.validators.MinValueValidator(0)])),
                ('trade_date', models.DateField()),
                ('notes', models.CharField(blank=True, max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('ticker', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='lots', to='market.ticker')),
            ],
            options={'ordering': ['-trade_date', '-id']},
        ),
        migrations.CreateModel(
            name='CachedQuote',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('symbol', models.CharField(max_length=10)),
                ('data', models.JSONField()),
                ('fetched_at', models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.AddConstraint(
            model_name='cachedquote',
            constraint=models.UniqueConstraint(fields=('symbol',), name='unique_cached_symbol'),
        ),
        migrations.AddIndex(
            model_name='cachedquote',
            index=models.Index(fields=['symbol'], name='market_cach_symbol_1c5d40_idx'),
        ),
    ]

