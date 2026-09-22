from pathlib import Path
import os
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

fonts_dir = "C:/Windows/Fonts"
pdfmetrics.registerFont(TTFont("ARIAL", os.path.join(fonts_dir, "arial.ttf")))
pdfmetrics.registerFont(TTFont("ARIAL-BOLD", os.path.join(fonts_dir, "arialbd.ttf")))
cour_path = None
for f in os.listdir(fonts_dir):
    if f.lower().startswith("cour") and "bd" not in f.lower() and "i" not in f.lower():
        cour_path = os.path.join(fonts_dir, f)
        break
if cour_path:
    pdfmetrics.registerFont(TTFont("COURIER", cour_path))

OUT = "docs/Documento-Forma-A.pdf"
styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="BodyES", parent=styles["BodyText"], leading=16, spaceAfter=10, fontName="ARIAL", fontSize=11, alignment=TA_JUSTIFY))
styles.add(ParagraphStyle(name="TitleES", parent=styles["Title"], leading=28, spaceAfter=18, fontName="ARIAL-BOLD", fontSize=20, textColor=colors.HexColor("#1a3a6b")))
styles.add(ParagraphStyle(name="Heading1ES", parent=styles["Heading1"], leading=22, spaceAfter=10, fontName="ARIAL-BOLD", fontSize=15, textColor=colors.HexColor("#1a3a6b")))
styles.add(ParagraphStyle(name="Heading2ES", parent=styles["Heading2"], leading=20, spaceAfter=8, fontName="ARIAL-BOLD", fontSize=13, textColor=colors.HexColor("#1a3a6b")))
styles.add(ParagraphStyle(name="BulletES", parent=styles["BodyText"], leading=16, spaceAfter=4, fontName="ARIAL", fontSize=11, alignment=TA_JUSTIFY))
styles.add(ParagraphStyle(name="CodeES", parent=styles["BodyText"], leading=12, spaceAfter=4, fontName="COURIER", fontSize=8.5))

def p(text, style="BodyES"):
    if isinstance(style, ParagraphStyle):
        return Paragraph(text, style)
    return Paragraph(text, styles[style])

def bullet(text):
    return Paragraph(f"<bullet>&bull;</bullet> {text}", styles["BulletES"])

def code_block(text):
    return Paragraph(f"<font name='COURIER' size='8'>{text}</font>", styles["CodeES"])

pages = [
    [Spacer(1, 4 * cm), p("Forma A", "TitleES"),
     p("Sistema de Gesti&#243;n de Cursos y Matr&#237;culas", ParagraphStyle("sub", parent=styles["TitleES"], fontSize=14, textColor=colors.HexColor("#333"), spaceAfter=6)),
     p("Informe de Integraci&#243;n de Sistemas", ParagraphStyle("sub2", parent=styles["BodyES"], fontSize=14, spaceAfter=6)),
     Spacer(1, 2 * cm),
     p("<b>Dominio:</b> Forma A"),
     p("<b>Grupo:</b> Forma A"),
     p("<b>Integrantes:</b> [Integrante 1], [Integrante 2], [Integrante 3]"),
     p("<b>Asignatura:</b> Integraci&#243;n de Sistemas"),
     p("<b>Fecha:</b> Septiembre 2026"),
     p("<b>Universidad de Concepci&#243;n &#8212; Facultad de Ingenier&#237;a</b>")],

    [p("1. An&#225;lisis del problema", "TitleES"),
     p("AprendeM&#225;s opera dos sistemas que evolucionaron por separado. <b>Cupos</b> conoce la oferta de cursos y la capacidad restante; <b>Matr&#237;culas</b> guarda estudiantes y sus inscripciones. Sin integraci&#243;n, una matr&#237;cula puede exceder la capacidad de una sala."),
     p("La necesidad es que una matr&#237;cula solo se confirme si Cupos la autoriza. Las restricciones relevantes son: API p&#250;blica versionada, contrato formal, servicios y bases independientes, autenticaci&#243;n y comportamiento seguro ante una dependencia ca&#237;da."),
     p("Se construy&#243; una soluci&#243;n deliberadamente acotada: no intenta introducir una transacci&#243;n distribuida. En cambio, la decisi&#243;n de ocupar se mantiene at&#243;mica dentro de Cupos y la API informa con precisi&#243;n los errores recuperables.")],

    [p("2. Dise&#241;o y arquitectura", "TitleES"),
     p("Matr&#237;culas recibe HTTP REST bajo /v1. Mantiene estudiantes y matr&#237;culas en SQLite. Para verificar disponibilidad usa un canal gRPC reutilizable contra Cupos, que posee una segunda base SQLite. Redis es infraestructura compartida de cach&#237; e idempotencia, no fuente de verdad acad&#233;mica."),
     p("<b>Cliente HTTP &#8594; Matr&#237;culas (REST) &#8594; Cupos (gRPC/protobuf)</b>"),
     p("Esta estructura reduce el acoplamiento de datos: Matr&#237;culas persiste el identificador del curso, pero nunca una copia administrable de sus cupos. Docker Compose declara los tres contenedores y variables de conexi&#243;n.")],

    [p("3. ADR-001: frontera de servicios (D1)", "Heading1ES"),
     p("<b>Contexto:</b> Cupos y Matr&#237;culas tienen propietarios y datos con sensibilidad diferente. Alternativas: monolito y base com&#250;n; procesos separados con base com&#250;n; dos servicios con base por servicio."),
     p("<b>Decisi&#243;n:</b> se eligieron dos servicios con bases separadas. Cupos posee Curso y sus contadores; Matr&#237;culas posee Estudiante y Matr&#237;cula. La frontera evita que un cambio al esquema de cupos afecte al historial de matr&#237;culas."),
     p("<b>Costo aceptado:</b> la operaci&#243;n cruza la red y puede requerir conciliaci&#243;n si falla tras ocupar un cupo. Producci&#243;n evolucionar&#237;a hacia reserva identificada y proceso de compensaci&#243;n, no hacia acceso cruzado a datos.")],

    [p("4. ADR-002: REST y gRPC (D2)", "Heading1ES"),
     p("<b>Alternativas:</b> REST/JSON para todo, gRPC para todo, o REST externo con gRPC interno. Se eligi&#243; la &#250;ltima opci&#243;n: REST permite a portal y personal usar verbos, c&#243;digos y JSON; gRPC genera stubs tipados y ofrece streaming para el cat&#225;logo."),
     p("El experimento local midi&#243; que el Curso de prueba ocupa <b>39 bytes en protobuf contra 94 bytes JSON</b>. Esa diferencia apoya usar protobuf en el tramo interno repetido."),
     p("<b>Modo de invocaci&#243;n:</b> se utiliza <b>unary-unary s&#237;ncrono</b> para ConsultarCurso, OcuparCupo y LiberarCupo. El cliente Matr&#237;culas necesita el resultado inmediato para continuar su l&#243;gica de negocio. ListarCursos usa <b>server streaming</b> porque el cat&#225;logo puede crecer."),
     p("<b>Costo:</b> hay dos contratos que mantener. Se mitiga con cupos.proto y openapi.yaml versionados y con pruebas autom&#225;ticas de su estructura.")],

    [p("5. ADR-003: contrato y evoluci&#243;n (D3)", "Heading1ES"),
     p("REST usa /v1; cambios incompatibles se publican en /v2 con una ventana de deprecaci&#243;n comunicada. Agregar un atributo opcional es compatible, pero modificar sem&#225;tica o eliminar uno requerido requiere versi&#243;n nueva."),
     p("En protobuf los campos reciben n&#250;meros estables. Una futura descripcion = 5 es compatible, pero renumerar cupos_disponibles no lo es.")],

    [p("6. ADR-004: resiliencia (D4)", "Heading1ES"),
     p("Sin timeout, una dependencia lenta puede consumir los recursos de Matr&#237;culas. Con disponibilidad basada solo en cach&#237; se podr&#237;a sobrepasar la sala. Se eligi&#243; <b>fail-fast</b>: deadline gRPC de 2 segundos, 503 para UNAVAILABLE y 504 para DEADLINE_EXCEEDED."),
     p("Los errores usan <b>application/problem+json</b> con type, title, status y detail. RFC 9457 estandariza esta representaci&#243;n para que clientes HTTP reciban detalle accionable sin una traza de implementaci&#243;n."),
     p("<b>Costo:</b> se rechaza temporalmente una matr&#237;cula que podr&#237;a completar m&#225;s tarde. El cliente debe reintentar con Idempotency-Key.")],

    [p("7. ADR-005: autenticaci&#243;n Bearer", "Heading1ES"),
     p("<b>Alternativas:</b> Basic Auth expone credenciales en cada petici&#243;n; API Key en query string queda expuesta en URLs y logs; Bearer Token usa un token previamente acordado sin credenciales por petici&#243;n."),
     p("<b>Decisi&#243;n:</b> se eligi&#243; <b>Bearer Token</b> con API Key est&#225;tica para desarrollo y tokens rotables en producci&#243;n. Se declara en el contrato OpenAPI como securitySchemes: bearerAuth y se aplica globalmente."),
     p("<b>Justificaci&#243;n:</b> est&#225;ndar RFC 6750, soportado nativamente por OpenAPI 3.0; sin credenciales por petici&#243;n; migr&#225;vel a JWT sin cambiar la estructura del header.")],

    [p("8. Experimento: serializaci&#243;n (Competencia 6)", "Heading1ES"),
     p("<b>Hip&#243;tesis:</b> la representaci&#243;n protobuf del mismo Curso utiliza menos bytes y un tiempo de serializaci&#243;n significativamente menor que su equivalente en JSON."),
     p("<b>M&#233;todo:</b> 10 series de 10.000 serializaciones por formato, midiendo con time.perf_counter_ns() y len()."),
     p("<b>Tabla de resultados:</b>"),
     Table([["Formato", "Tama&#241;o", "Media (ns/op)", "Desv. est&#225;ndar"],
            ["Protobuf", "39 B", "238", "&#177; 72"],
            ["JSON compacto", "94 B", "3.770", "&#177; 273"]],
           colWidths=[4*cm, 3*cm, 4*cm, 4*cm],
           style=TableStyle([("GRID", (0,0), (-1,-1), .5, colors.grey),
                            ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#1a3a6b")),
                            ("TEXTCOLOR", (0,0), (-1,0), colors.white),
                            ("ALIGN", (1,1), (-1,-1), "CENTER"),
                            ("VALIGN", (0,0), (-1,-1), "MIDDLE")])),
     Spacer(1, 0.5*cm),
     p("<b>Resultado:</b> protobuf fue 58,5 % menor por mensaje y m&#225;s r&#225;pido.")],

    [p("9. Consideraciones de contexto (Competencia 2)", "Heading1ES"),
     p("<b>Factor elegido:</b> privacidad de datos estudiantiles."),
     p("<b>Influencia en el dise&#241;o:</b>"),
     bullet("Separa la base de Matr&#237;culas de la de Cupos para limitar la exposici&#243;n de nombres y correos al servicio de Cupos."),
     bullet("Toda la API REST exige Bearer token para acceder a recursos de estudiantes y matr&#237;culas."),
     bullet("Los mensajes de error no incluyen stack traces, devolviendo application/problem+json gen&#233;ricos."),
     bullet("Cupos nunca recibe datos personales; solo recibe identificadores de curso."),
     p("<b>Costo:</b> tres contenedores m&#225;s Redis, comunicaci&#243;n por red entre servicios y gesti&#243;n de tokens.")],

    [p("10. Ejecuci&#243;n con Docker", "Heading1ES"),
     p("<b>Requisitos previos:</b> Docker Desktop instalado y en ejecuci&#243;n."),
     p("<b>Levantar el sistema:</b>"),
     code_block("docker compose up --build"),
     p("Este comando construye y levanta los tres contenedores:"),
     bullet("Cupos: servicio gRPC en puerto 50051"),
     bullet("Matr&#237;culas: API REST en puerto 8000"),
     bullet("Redis: cach&#237; e idempotencia en puerto 6379"),
     p("<b>Verificaci&#243;n:</b> la API est&#225; en http://localhost:8000 y Swagger en /docs."),
     p("<b>Probar resiliencia:</b> ejecutar <b>docker compose stop cupos</b> y consultar o crear una matr&#237;cula; se espera una respuesta HTTP 503 con application/problem+json."),
     p("<b>Ejemplo de uso:</b>"),
     code_block("$headers = @{ Authorization = 'Bearer desarrollo-seguro' }&#10;$e = Invoke-RestMethod http://localhost:8000/v1/estudiantes -Method Post -Headers $headers -ContentType application/json -Body '{\"nombre\":\"Ana Perez\",\"email\":\"ana@example.com\"}'&#10;$m = Invoke-RestMethod http://localhost:8000/v1/matriculas -Method Post -Headers $headers -ContentType application/json -Body \"{\\\"estudiante_id\\\":\\\"$($e.id)\\\",\\\"curso_id\\\":\\\"ARQ-101\\\"}\""),
     p("<b>Pruebas:</b> cuatro pruebas automatizadas pasan: ciclo de ocupar/liberar cupo, curso inexistente, contrato gRPC con streaming, y validaci&#243;n de OpenAPI con Bearer y problem+JSON.")],

    [p("11. Reflexi&#243;n final", "Heading1ES"),
     p("<b>&#191;Qu&#233;har&#237;an distinto?</b>"),
     bullet("Implementar un sistema de reserva durable con saga pattern para el fallo entre servicios."),
     bullet("A&#241;adir observabilidad con m&#233;tricas (Prometheus) y trazabilidad distribuida (OpenTelemetry)."),
     bullet("Realizar pruebas de integraci&#243;n reales en contenedores Docker."),
     bullet("Implementar TLS entre servicios y rotaci&#243;n autom&#225;tica de tokens."),
     p("<b>&#191;&#191;Qu&#233; qued&#243; pendiente?</b>"),
     bullet("Conciliaci&#243;n de fallo parcial: OcuparCupo succeede pero el INSERT de matr&#237;cula falla."),
     bullet("Pol&#237;tica de retenci&#243;n de datos y auditor&#237;a de operaciones."),
     bullet("Escalamiento horizontal: SQLite no es adecuado para m&#250;ltiples instancias; se requerir&#237;a PostgreSQL."),
     bullet("Rate limiting y health checks avanzados."),
     Spacer(1, 1*cm),
     p("La soluci&#243;n evita la sobreconstrucci&#243;n y cumple con todos los requisitos funcionales y de arquitectura planteados.")],

    [p("12. Estructura del repositorio", "Heading1ES"),
     code_block("tarea-1/\n&#124;&#8211; docker-compose.yml\n&#124;&#8211; matriculas/\n&#124;&nbsp;&nbsp;&nbsp;&nbsp;&#124;&#8211; Dockerfile\n&#124;&nbsp;&nbsp;&nbsp;&nbsp;&#124;&#8211; requirements.txt\n&#124;&nbsp;&nbsp;&nbsp;&nbsp;&#124;&#8211; openapi.yaml\n&#124;&nbsp;&nbsp;&nbsp;&nbsp;&#124;&nbsp;&nbsp;&nbsp;&nbsp;__init__.py\n&#124;&nbsp;&nbsp;&nbsp;&nbsp;&#124;&nbsp;&nbsp;&nbsp;&nbsp;main.py\n&#124;&nbsp;&nbsp;&nbsp;&nbsp;&#124;&nbsp;&nbsp;&nbsp;&nbsp;database.py\n&#124;&nbsp;&nbsp;&nbsp;&nbsp;&#124;&nbsp;&nbsp;&nbsp;&nbsp;grpc_client.py\n&#124;&nbsp;&nbsp;&nbsp;&nbsp;&#124;&nbsp;&nbsp;&nbsp;&nbsp;cupos_pb2.py\n&#124;&nbsp;&nbsp;&nbsp;&nbsp;&#124;&nbsp;&nbsp;&nbsp;&nbsp;cupos_pb2_grpc.py\n&#124;&nbsp;&nbsp;&nbsp;&nbsp;cupos/\n&#124;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Dockerfile\n&#124;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;cupos.proto\n&#124;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;server.py\n&#124;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;database.py\n&#124;&nbsp;&nbsp;&nbsp;&nbsp;tests/\n&#124;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;test_cupos.py\n&#124;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;test_contracts.py\n&#124;&nbsp;&nbsp;&nbsp;&nbsp;docs/\n&#124;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;adr/\n&#124;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;ADR-001-frontera-servicios.md\n&#124;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;ADR-002-rest-grpc.md\n&#124;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;ADR-003-versionado.md\n&#124;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;ADR-004-resiliencia.md\n&#124;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;ADR-005-autenticacion.md\n&#124;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;experimento_serializacion.py\n&#124;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;generar_informe.py\n&#124;&nbsp;&nbsp;&nbsp;&nbsp;requirements-dev.txt\n&#124;&nbsp;&nbsp;&nbsp;&nbsp;README.md")],

    [p("13. Referencias", "Heading1ES"),
     p("[1] gRPC. Performance Best Practices. https://grpc.io/docs/guides/performance/"),
     p("[2] Protocol Buffers. Language Guide (proto3). https://protobuf.dev/programming-guides/proto3/"),
     p("[3] IETF. RFC 9457: Problem Details for HTTP APIs. https://www.rfc-editor.org/rfc/rfc9457.html"),
     p("[4] Redis. Cache-aside. https://redis.io/docs/latest/develop/use-cases/cache-aside/"),
     p("[5] OpenAPI Specification. https://swagger.io/specification/"),
     Spacer(1, 1*cm),
     p("Anexos del repositorio: openapi.yaml, cupos.proto, cinco ADR, pruebas y guion de video.")],
]

story = []
for index, content in enumerate(pages):
    story.extend(content)
    if index != len(pages) - 1:
        story.append(PageBreak())

doc = SimpleDocTemplate(OUT, pagesize=letter, leftMargin=2.2*cm, rightMargin=2.2*cm, topMargin=2*cm, bottomMargin=2*cm)
doc.build(story)
print("PDF generated:", OUT)
print("Size:", os.path.getsize(OUT), "bytes")

from pypdf import PdfReader
reader = PdfReader(OUT)
print("Pages:", len(reader.pages))
