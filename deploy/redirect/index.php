<?php
// Sube la Pi con url.txt; esto solo reenvía a la dirección actual del túnel.
header("Cache-Control: no-store");
$u = trim(@file_get_contents(__DIR__ . "/url.txt"));
if (preg_match('~^https://[a-z0-9.-]+\.(trycloudflare\.com|[a-z0-9-]+\.[a-z]+)(/|$)~i', $u)) {
    header("Location: " . $u, true, 302);
    exit;
}
http_response_code(503);
?><!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ALCI</title><body style="font-family:system-ui;max-width:30rem;margin:4rem auto;padding:0 1rem">
<h1>ALCI está fuera de línea</h1><p>El equipo no ha avisado su dirección. Revisa que esté encendido y con internet; vuelve a intentar en unos minutos.</p></body></html>
