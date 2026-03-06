import os
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from jinja2 import Environment, FileSystemLoader, StrictUndefined


class Command(BaseCommand):
    help = (
        "Render nginx/default.conf from a Jinja2 template using "
        "NGINX_PROXY_HOST from environment (or --host)."
    )

    def add_arguments(self, parser):
        repo_root = Path(__file__).resolve().parents[4]
        parser.add_argument(
            "--template",
            default=str(repo_root / "nginx" / "default.conf.j2"),
            help="Path to the Jinja2 nginx config template.",
        )
        parser.add_argument(
            "--output",
            default=str(repo_root / "nginx" / "default.conf"),
            help="Path where the rendered nginx config should be written.",
        )
        parser.add_argument(
            "--host",
            dest="host_header",
            default=None,
            help=(
                "Host header value to inject, e.g. 'example.com:8000'. "
                "Overrides NGINX_PROXY_HOST."
            ),
        )
        parser.add_argument(
            "--check",
            action="store_true",
            help="Only validate rendering inputs and print the target paths.",
        )

    def handle(self, *args, **options):
        template_path = Path(options["template"]).resolve()
        output_path = Path(options["output"]).resolve()

        host_header = (options.get("host_header") or os.getenv("NGINX_PROXY_HOST", "")).strip()
        if not host_header:
            raise CommandError(
                "Missing host header value. Set NGINX_PROXY_HOST or pass --host."
            )

        if not template_path.exists():
            raise CommandError(f"Template not found: {template_path}")

        env = Environment(
            loader=FileSystemLoader(str(template_path.parent)),
            undefined=StrictUndefined,
            autoescape=False,
            keep_trailing_newline=True,
        )
        template = env.get_template(template_path.name)
        rendered = template.render(host_header=host_header)

        if options.get("check"):
            self.stdout.write(
                self.style.SUCCESS(
                    f"Template OK. host_header={host_header}, template={template_path}, output={output_path}"
                )
            )
            return

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")

        self.stdout.write(
            self.style.SUCCESS(
                f"Rendered nginx config to {output_path} using host_header={host_header}"
            )
        )

