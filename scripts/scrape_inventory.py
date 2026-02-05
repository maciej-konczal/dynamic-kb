"""Scrape car dealership inventory and generate a markdown report."""
import asyncio
import re
from dataclasses import dataclass
from crawl4ai import AsyncWebCrawler


@dataclass
class CarListing:
    """Parsed car listing data."""
    url: str
    title: str = ""
    price: str = ""
    year: str = ""
    mileage: str = ""
    fuel: str = ""
    # Detailed fields (from individual page)
    engine: str = ""
    power: str = ""
    transmission: str = ""
    drive: str = ""
    body_type: str = ""
    color: str = ""
    doors: str = ""
    seats: str = ""
    condition: str = ""
    registration: str = ""
    description: str = ""
    equipment: list = None

    def __post_init__(self):
        if self.equipment is None:
            self.equipment = []


def extract_listing_urls(markdown: str) -> list[str]:
    """Extract individual car listing URLs from inventory page."""
    # Pattern matches otomoto offer URLs
    pattern = r'https://www\.otomoto\.pl/osobowe/oferta/[^\s\)\"\'>\]]+\.html'
    urls = re.findall(pattern, markdown)
    # Deduplicate while preserving order
    seen = set()
    unique = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique.append(url)
    return unique


def parse_car_details(markdown: str, url: str) -> CarListing:
    """Parse car details from individual listing page."""
    car = CarListing(url=url)

    # Extract title - look for pattern like "# Volkswagen Arteon..."
    title_match = re.search(r'# (Volkswagen [^\n]+)', markdown)
    if title_match:
        car.title = title_match.group(1).strip()
    else:
        # Fallback: extract from URL
        url_match = re.search(r'/oferta/([^/]+)-ID', url)
        if url_match:
            car.title = url_match.group(1).replace('-', ' ').title()

    # Extract price
    price_match = re.search(r'(\d[\d\s]*(?:\d{3}))\s*PLN', markdown)
    if price_match:
        car.price = price_match.group(1).replace(' ', ' ') + " PLN"

    # Key specs from "Najważniejsze" section or details
    specs_patterns = {
        'mileage': r'Przebieg\s*\n?\s*([\d\s]+\s*km)',
        'fuel': r'Rodzaj paliwa\s*\n?\s*(\w+)',
        'transmission': r'Skrzynia biegów\s*\n?\s*(\w+)',
        'body_type': r'Typ nadwozia\s*\n?\s*(\w+)',
        'engine': r'Pojemność skokowa\s*\n?\s*([\d\s]+\s*cm)',
        'power': r'Moc\s*\n?\s*([\d\s]+\s*KM)',
        'year': r'Rok produkcji\s*\n?\s*(\d{4})',
        'color': r'Kolor\s*\n?\s*(\w+)',
        'doors': r'Liczba drzwi\s*\n?\s*(\d+)',
        'seats': r'Liczba miejsc\s*\n?\s*(\d+)',
        'drive': r'Napęd\s*\n?\s*([^\n]+)',
        'condition': r'Stan\s*\n?\s*(\w+)',
        'registration': r'Numer rejestracyjny pojazdu\s*\n?\s*(\w+)',
    }

    for field, pattern in specs_patterns.items():
        match = re.search(pattern, markdown, re.IGNORECASE)
        if match:
            setattr(car, field, match.group(1).strip())

    # Extract description
    desc_match = re.search(r'## Opis\s*\n(?:Zgłoś\s*\n)?(.*?)(?=\n##|\nPokaż pełny opis)', markdown, re.DOTALL)
    if desc_match:
        desc = desc_match.group(1).strip()
        # Clean up the description
        desc = re.sub(r'\*+', '', desc)  # Remove asterisks
        desc = re.sub(r'\\+', '', desc)  # Remove backslashes
        desc = re.sub(r'\n{3,}', '\n\n', desc)  # Normalize newlines
        car.description = desc[:1000]  # Limit length

    # Extract equipment items
    equipment_section = re.search(r'## Wyposażenie\s*\n(.*?)(?=\n##|$)', markdown, re.DOTALL)
    if equipment_section:
        # Find all equipment items (lines that look like features)
        items = re.findall(r'^([A-ZŻŹĆĄĘŁÓŚŃ][^\n]{3,50})$', equipment_section.group(1), re.MULTILINE)
        car.equipment = [item.strip() for item in items if item.strip()][:20]  # Limit to 20 items

    return car


def generate_markdown_report(cars: list[CarListing], dealer_name: str) -> str:
    """Generate a markdown report from car listings."""
    lines = [
        f"# {dealer_name} - Inventory",
        "",
        f"*Generated inventory report with {len(cars)} vehicles*",
        "",
        "---",
        "",
    ]

    # Summary table
    lines.extend([
        "## Quick Overview",
        "",
        "| # | Model | Year | Mileage | Fuel | Price |",
        "|---|-------|------|---------|------|-------|",
    ])

    for i, car in enumerate(cars, 1):
        lines.append(f"| {i} | {car.title} | {car.year} | {car.mileage} | {car.fuel} | {car.price} |")

    lines.extend(["", "---", ""])

    # Detailed sections for each car
    for i, car in enumerate(cars, 1):
        lines.extend([
            f"## {i}. {car.title}",
            "",
            f"**Price:** {car.price}",
            "",
            "### Specifications",
            "",
            "| Spec | Value |",
            "|------|-------|",
            f"| Year | {car.year} |",
            f"| Mileage | {car.mileage} |",
            f"| Fuel Type | {car.fuel} |",
            f"| Engine | {car.engine} |",
            f"| Power | {car.power} |",
            f"| Transmission | {car.transmission} |",
            f"| Drive | {car.drive} |",
            f"| Body Type | {car.body_type} |",
            f"| Color | {car.color} |",
            f"| Doors / Seats | {car.doors} / {car.seats} |",
            f"| Condition | {car.condition} |",
            f"| Registration | {car.registration} |",
            "",
        ])

        if car.description:
            lines.extend([
                "### Description",
                "",
                car.description,
                "",
            ])

        if car.equipment:
            lines.extend([
                "### Equipment",
                "",
            ])
            for item in car.equipment:
                lines.append(f"- {item}")
            lines.append("")

        lines.extend([
            f"[View listing]({car.url})",
            "",
            "---",
            "",
        ])

    return "\n".join(lines)


async def scrape_inventory(inventory_url: str, output_path: str):
    """Main function to scrape inventory and generate report."""
    print(f"Scraping inventory: {inventory_url}")

    async with AsyncWebCrawler() as crawler:
        # Step 1: Get inventory page
        print("Fetching inventory page...")
        inventory_result = await crawler.arun(url=inventory_url, page_timeout=60000)

        if not inventory_result.success:
            print(f"Failed to fetch inventory: {inventory_result}")
            return

        # Extract dealer name
        dealer_match = re.search(r'## ([^\n]+)\n', inventory_result.markdown)
        dealer_name = dealer_match.group(1) if dealer_match else "Car Dealership"
        print(f"Dealer: {dealer_name}")

        # Step 2: Extract listing URLs
        listing_urls = extract_listing_urls(inventory_result.markdown)
        print(f"Found {len(listing_urls)} car listings")

        # Step 3: Fetch each listing
        cars = []
        for i, url in enumerate(listing_urls, 1):
            print(f"  [{i}/{len(listing_urls)}] Fetching: {url[:60]}...")
            try:
                result = await crawler.arun(url=url, page_timeout=60000)
                if result.success and result.markdown:
                    car = parse_car_details(result.markdown, url)
                    cars.append(car)
                    print(f"    ✓ {car.title} - {car.price}")
                else:
                    print(f"    ✗ Failed to fetch")
            except Exception as e:
                print(f"    ✗ Error: {e}")

        # Step 4: Generate report
        print(f"\nGenerating markdown report...")
        report = generate_markdown_report(cars, dealer_name)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(report)

        print(f"✓ Report saved to: {output_path}")
        print(f"  Total cars: {len(cars)}")


if __name__ == "__main__":
    import sys
    from pathlib import Path

    url = sys.argv[1] if len(sys.argv) > 1 else "https://mroczkowski.otomoto.pl/inventory"
    default_output = Path(__file__).parent.parent / "inventory_report.md"
    output = sys.argv[2] if len(sys.argv) > 2 else str(default_output)

    asyncio.run(scrape_inventory(url, output))
