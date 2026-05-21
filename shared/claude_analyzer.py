from __future__ import annotations

import json
import os
import time
from typing import Optional

from shared.models import AnalysisResult, ClientProfile, EnrichedJob, Job, Recommendation
from shared.utils import setup_logging

logger = setup_logging("claude_analyzer")

DEFAULT_SYSTEM_PROMPT = """Eres un filtro inteligente de relevancia laboral. Tu trabajo es RAZONAR sobre si un puesto es realmente adecuado para el candidato. NO te bases en coincidencia de palabras clave — usa lógica y sentido común.

Responde SOLO con un objeto JSON válido (sin markdown, sin ```):

{
  "relevance_score": <int 0-100>,
  "reasoning": "<1 oración: POR QUÉ es o no es relevante>",
  "summary": "<resumen de 1-2 oraciones del puesto>",
  "matching_skills": ["skill1", "skill2"],
  "missing_skills": ["skill1", "skill2"],
  "recommendation": "<APPLY_NOW si score >= 70 | CONSIDER si 40-69 | SKIP si < 40>"
}

PROCESO DE RAZONAMIENTO:
1. ¿El CAMPO del puesto coincide con el del candidato? (ej: "Distribución bancaria" NO es mecatrónica aunque diga "Analista")
2. ¿El NIVEL es accesible? (Si dice "Sr", "Senior", "Lead", "5+ años" y el candidato es practicante/junior → SKIP)
3. ¿El candidato podría REALMENTE hacer este trabajo con sus skills y formación?

IMPORTANTE: Una palabra genérica compartida ("analista", "técnico", "ingeniero", "junior") NO hace relevante un puesto. Lo que importa es: ¿este trabajo pertenece al MISMO MUNDO PROFESIONAL que el candidato?"""


def is_api_available() -> bool:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    return bool(key and key != "sk-ant-your-key-here")


def _get_prompt(custom_prompt: str | None) -> str:
    return custom_prompt if custom_prompt else DEFAULT_SYSTEM_PROMPT


def _build_user_message(profile: ClientProfile, job: Job) -> str:
    profile_text = f"""PERFIL DEL CANDIDATO:
Nombre: {profile.name}
Descripcion: {profile.description}
Roles objetivo (ejemplos): {', '.join(profile.target_roles[:20])}
Skills: {', '.join(profile.skills)}
Educacion: {profile.education}
Nivel: {profile.experience_level}
Ubicaciones preferidas: {', '.join(profile.preferred_locations)}"""

    job_text = f"""OFERTA DE TRABAJO:
Titulo: {job.title}
Empresa: {job.company}
Ubicacion: {job.location}
Tipo: {job.job_type.value}
Descripcion: {job.description[:1500] if job.description else 'No disponible'}"""

    return f"{profile_text}\n\n{job_text}"


def _parse_analysis(raw: str, job_id: str) -> Optional[AnalysisResult]:
    try:
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        data = json.loads(text)

        rec_str = data.get("recommendation", "SKIP").upper()
        rec = Recommendation.SKIP
        if rec_str == "APPLY_NOW":
            rec = Recommendation.APPLY_NOW
        elif rec_str == "CONSIDER":
            rec = Recommendation.CONSIDER

        return AnalysisResult(
            job_id=job_id,
            relevance_score=max(0, min(100, int(data.get("relevance_score", 0)))),
            summary=str(data.get("summary", "")),
            matching_skills=data.get("matching_skills", []),
            missing_skills=data.get("missing_skills", []),
            recommendation=rec,
        )
    except Exception as e:
        logger.warning("Error parseando respuesta Claude para job %s: %s", job_id, e)
        return None


def analyze_single_job(
    job: Job,
    profile: ClientProfile,
    model: str = "claude-haiku-4-5-20251001",
    max_tokens: int = 512,
    system_prompt: str | None = None,
) -> EnrichedJob:
    if not is_api_available():
        return EnrichedJob(job=job, analysis=None)

    prompt = _get_prompt(system_prompt)

    try:
        import anthropic
        client = anthropic.Anthropic()

        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=[{
                "type": "text",
                "text": prompt,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{
                "role": "user",
                "content": _build_user_message(profile, job),
            }],
        )

        raw_text = resp.content[0].text if resp.content else ""
        analysis = _parse_analysis(raw_text, job.id)
        return EnrichedJob(job=job, analysis=analysis)

    except Exception as e:
        logger.error("Error analizando job '%s': %s", job.title, e)
        return EnrichedJob(job=job, analysis=None)


def analyze_jobs_sequential(
    jobs: list[Job],
    profile: ClientProfile,
    model: str = "claude-haiku-4-5-20251001",
    max_tokens: int = 512,
    system_prompt: str | None = None,
) -> list[EnrichedJob]:
    if not is_api_available():
        logger.warning("API key no configurada. Retornando trabajos sin analisis.")
        return [EnrichedJob(job=job, analysis=None) for job in jobs]

    try:
        import anthropic
        from tqdm import tqdm
    except ImportError:
        logger.error("anthropic o tqdm no instalados")
        return [EnrichedJob(job=job, analysis=None) for job in jobs]

    prompt = _get_prompt(system_prompt)
    client = anthropic.Anthropic()
    enriched: list[EnrichedJob] = []

    for job in tqdm(jobs, desc="Analizando con Claude", unit="job"):
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=[{
                    "type": "text",
                    "text": prompt,
                    "cache_control": {"type": "ephemeral"},
                }],
                messages=[{
                    "role": "user",
                    "content": _build_user_message(profile, job),
                }],
            )

            raw_text = resp.content[0].text if resp.content else ""
            analysis = _parse_analysis(raw_text, job.id)
            enriched.append(EnrichedJob(job=job, analysis=analysis))

        except Exception as e:
            if "RateLimitError" in type(e).__name__:
                logger.warning("Rate limit - esperando 30s...")
                time.sleep(30)
            else:
                logger.error("Error analizando job '%s': %s", job.title, e)
            enriched.append(EnrichedJob(job=job, analysis=None))

    return enriched


def analyze_jobs_batch(
    jobs: list[Job],
    profile: ClientProfile,
    model: str = "claude-haiku-4-5-20251001",
    max_tokens: int = 512,
    poll_interval: int = 30,
    max_wait: int = 3600,
    system_prompt: str | None = None,
) -> list[EnrichedJob]:
    if not jobs:
        return []

    if not is_api_available():
        logger.warning("API key no configurada. Retornando trabajos sin analisis.")
        return [EnrichedJob(job=job, analysis=None) for job in jobs]

    try:
        import anthropic
    except ImportError:
        logger.error("anthropic no instalado")
        return [EnrichedJob(job=job, analysis=None) for job in jobs]

    prompt = _get_prompt(system_prompt)
    client = anthropic.Anthropic()

    requests = []
    for job in jobs:
        requests.append({
            "custom_id": job.id,
            "params": {
                "model": model,
                "max_tokens": max_tokens,
                "system": [{"type": "text", "text": prompt}],
                "messages": [{
                    "role": "user",
                    "content": _build_user_message(profile, job),
                }],
            },
        })

    logger.info("Enviando batch de %d trabajos a Claude API...", len(requests))

    try:
        batch = client.messages.batches.create(requests=requests)
        batch_id = batch.id
        logger.info("Batch creado: %s", batch_id)
    except Exception as e:
        logger.error("Error creando batch: %s. Usando modo secuencial.", e)
        return analyze_jobs_sequential(jobs, profile, model, max_tokens, system_prompt)

    elapsed = 0
    while elapsed < max_wait:
        try:
            status = client.messages.batches.retrieve(batch_id)
            if status.processing_status == "ended":
                logger.info("Batch completado!")
                break
            logger.info("Batch en progreso... (%ds)", elapsed)
        except Exception as e:
            logger.warning("Error consultando batch: %s", e)

        time.sleep(poll_interval)
        elapsed += poll_interval

    if elapsed >= max_wait:
        logger.warning("Batch timeout despues de %ds. Retornando sin analisis.", max_wait)
        return [EnrichedJob(job=job, analysis=None) for job in jobs]

    job_map = {job.id: job for job in jobs}
    enriched: list[EnrichedJob] = []

    try:
        for result in client.messages.batches.results(batch_id):
            job_id = result.custom_id
            job = job_map.pop(job_id, None)
            if not job:
                continue

            analysis = None
            if result.result.type == "succeeded":
                msg = result.result.message
                raw_text = msg.content[0].text if msg.content else ""
                analysis = _parse_analysis(raw_text, job_id)

            enriched.append(EnrichedJob(job=job, analysis=analysis))
    except Exception as e:
        logger.error("Error leyendo resultados del batch: %s", e)

    for remaining_job in job_map.values():
        enriched.append(EnrichedJob(job=remaining_job, analysis=None))

    return enriched


def analyze_jobs(
    jobs: list[Job],
    profile: ClientProfile,
    model: str = "claude-haiku-4-5-20251001",
    max_tokens: int = 512,
    use_batch: bool = True,
    system_prompt: str | None = None,
) -> list[EnrichedJob]:
    if not jobs:
        return []

    if not is_api_available():
        logger.warning("ANTHROPIC_API_KEY no encontrada o invalida. Los trabajos se mostraran sin score de relevancia.")
        return [EnrichedJob(job=job, analysis=None) for job in jobs]

    logger.info("Analizando %d trabajos con Claude (%s)...", len(jobs), model)

    if use_batch and len(jobs) >= 5:
        return analyze_jobs_batch(jobs, profile, model, max_tokens, system_prompt=system_prompt)
    else:
        return analyze_jobs_sequential(jobs, profile, model, max_tokens, system_prompt=system_prompt)
