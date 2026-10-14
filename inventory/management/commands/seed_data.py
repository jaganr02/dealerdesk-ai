"""
Management command to seed catalogue, inventory, and dealer data.
Fully idempotent and reconciled with VIKMO DealerDesk API_CONTRACT.md.
"""

import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from inventory.models import Dealer, Inventory, Product


class Command(BaseCommand):
    help = "Idempotently seed catalogue, inventory, and dealer data from CSV files."

    def add_arguments(self, parser):
        parser.add_argument(
            "--catalogue",
            type=str,
            default=str(settings.BASE_DIR / "data" / "catalogue.csv"),
            help="Path to catalogue.csv file (default: data/catalogue.csv)",
        )
        parser.add_argument(
            "--dealers",
            type=str,
            default=str(settings.BASE_DIR / "data" / "dealers.csv"),
            help="Path to dealers.csv file (default: data/dealers.csv)",
        )

    def handle(self, *args, **options):
        catalogue_path = Path(options["catalogue"])
        dealers_path = Path(options["dealers"])

        self.stdout.write(self.style.NOTICE("Starting DealerDesk database seeding..."))

        # Verify file existence
        if not catalogue_path.is_file():
            raise CommandError(f"Catalogue file not found at: {catalogue_path}")
        if not dealers_path.is_file():
            raise CommandError(f"Dealers file not found at: {dealers_path}")

        with transaction.atomic():
            prod_created, prod_updated, inv_created, inv_updated = self.seed_catalogue(catalogue_path)
            dealer_created, dealer_updated = self.seed_dealers(dealers_path)

        self.stdout.write(self.style.SUCCESS("\n--- Database Seeding Summary ---"))
        self.stdout.write(
            f"Products   : {prod_created} created, {prod_updated} updated (Total: {prod_created + prod_updated})"
        )
        self.stdout.write(
            f"Inventories: {inv_created} created, {inv_updated} updated (Total: {inv_created + inv_updated})"
        )
        self.stdout.write(
            f"Dealers    : {dealer_created} created, {dealer_updated} updated (Total: {dealer_created + dealer_updated})"
        )
        self.stdout.write(self.style.SUCCESS("Database seeding completed successfully.\n"))

    def seed_catalogue(self, file_path: Path):
        """Seed Product catalogue and 1:1 Inventory records from catalogue.csv."""
        self.stdout.write(f"Reading catalogue from: {file_path}")

        try:
            with open(file_path, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                required_cols = {"sku", "name", "price", "stock"}
                if not required_cols.issubset(set(reader.fieldnames or [])):
                    missing = required_cols - set(reader.fieldnames or [])
                    raise CommandError(
                        f"Catalogue CSV missing required columns: {missing}. Found: {reader.fieldnames}"
                    )

                prod_created = 0
                prod_updated = 0
                inv_created = 0
                inv_updated = 0

                for line_num, row in enumerate(reader, start=2):
                    sku = row.get("sku", "").strip()
                    name = row.get("name", "").strip()
                    price_str = row.get("price", "").strip()
                    stock_str = row.get("stock", "").strip()

                    if not sku or not name:
                        raise CommandError(
                            f"Row {line_num} in catalogue.csv has empty SKU or Name."
                        )

                    try:
                        price = Decimal(price_str)
                    except (InvalidOperation, ValueError):
                        raise CommandError(
                            f"Row {line_num} in catalogue.csv has invalid price: '{price_str}'"
                        )

                    try:
                        stock = int(stock_str)
                        if stock < 0:
                            raise ValueError()
                    except ValueError:
                        raise CommandError(
                            f"Row {line_num} in catalogue.csv has invalid stock quantity: '{stock_str}'"
                        )

                    category = row.get("category", "").strip()
                    brand = row.get("brand", "").strip()
                    vehicle_fitment = row.get("vehicle_fitment", "").strip()
                    description = row.get("description", "").strip()

                    # Upsert Product
                    product, created = Product.objects.update_or_create(
                        sku=sku,
                        defaults={
                            "name": name,
                            "category": category,
                            "brand": brand,
                            "vehicle_fitment": vehicle_fitment,
                            "price": price,
                            "description": description,
                            "is_active": True,
                        },
                    )
                    if created:
                        prod_created += 1
                    else:
                        prod_updated += 1

                    # Upsert Inventory
                    _, inv_is_created = Inventory.objects.update_or_create(
                        product=product,
                        defaults={
                            "quantity": stock,
                        },
                    )
                    if inv_is_created:
                        inv_created += 1
                    else:
                        inv_updated += 1

                return prod_created, prod_updated, inv_created, inv_updated

        except Exception as e:
            if isinstance(e, CommandError):
                raise
            raise CommandError(f"Error reading {file_path}: {e}") from e

    def seed_dealers(self, file_path: Path):
        """Seed Dealer records from dealers.csv."""
        self.stdout.write(f"Reading dealers from: {file_path}")

        try:
            with open(file_path, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                required_cols = {"dealer_code", "name"}
                if not required_cols.issubset(set(reader.fieldnames or [])):
                    missing = required_cols - set(reader.fieldnames or [])
                    raise CommandError(
                        f"Dealers CSV missing required columns: {missing}. Found: {reader.fieldnames}"
                    )

                dealer_created = 0
                dealer_updated = 0

                for line_num, row in enumerate(reader, start=2):
                    dealer_code = row.get("dealer_code", "").strip()
                    name = row.get("name", "").strip()

                    if not dealer_code or not name:
                        raise CommandError(
                            f"Row {line_num} in dealers.csv has empty dealer_code or name."
                        )

                    city = row.get("city", "").strip()
                    phone = row.get("phone", "").strip()
                    email = row.get("email", "").strip()
                    gstin_raw = row.get("gstin", "").strip()
                    gstin = gstin_raw if gstin_raw else None

                    credit_str = row.get("credit_limit", "").strip()
                    credit_limit = Decimal("0.00")
                    if credit_str:
                        try:
                            credit_limit = Decimal(credit_str)
                        except (InvalidOperation, ValueError):
                            raise CommandError(
                                f"Row {line_num} in dealers.csv has invalid credit_limit: '{credit_str}'"
                            )

                    _, created = Dealer.objects.update_or_create(
                        dealer_code=dealer_code,
                        defaults={
                            "name": name,
                            "city": city,
                            "phone": phone,
                            "email": email,
                            "gstin": gstin,
                            "credit_limit": credit_limit,
                            "is_active": True,
                        },
                    )
                    if created:
                        dealer_created += 1
                    else:
                        dealer_updated += 1

                return dealer_created, dealer_updated

        except Exception as e:
            if isinstance(e, CommandError):
                raise
            raise CommandError(f"Error reading {file_path}: {e}") from e
