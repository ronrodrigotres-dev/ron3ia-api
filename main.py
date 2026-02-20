import grpc
import google.auth
from google.auth.transport.requests import Request
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

# Autenticación y corrección de credenciales gRPC
credentials, project_id = google.auth.default()
if not credentials.valid:
    credentials.refresh(Request())

ssl_creds = grpc.ssl_channel_credentials()
auth_creds = grpc.metadata_call_credentials(
    lambda context, callback: callback([("authorization", f"Bearer {credentials.token}")], None)
)
combined_creds = grpc.composite_channel_credentials(ssl_creds, auth_creds)

otlp_exporter = OTLPSpanExporter(
    endpoint="telemetry.googleapis.com:443",
    credentials=combined_creds
)
print("RON3IA Backend: Telemetría configurada correctamente.")
