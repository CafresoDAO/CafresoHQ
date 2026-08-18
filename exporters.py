"""Export / generate endpoints — extracted from serve.py.

PowerPoint / Word / PDF exporters and the image/video generators. Written as
plain functions taking serve.py's request handler as `self` and bound onto
its Handler class, so self._send_json / self._read_json etc. resolve there.
serve.py injects _vault_root as a zero-arg callable after import — the vault
root is settable from the UI, so a snapshot would go stale.
"""
import base64
import json
import uuid
import sys
import secrets
import os
import pathlib
import re
import subprocess
import tempfile
import time
import urllib.request

# Injected by serve.py right after import.
_vault_root = None
# Also injected by serve.py, and called WITHOUT a None-guard on purpose: if
# the injection is ever lost, every export door should fail loudly rather
# than quietly go back to filing deliverables the Library can never list
# (#141 — the write doors learned this question in #140; these five doors
# ride a different resolver and had never been asked it).
_vault_hidden_part = None





# ---- Export endpoints (PowerPoint / Word / PDF) ----------------------
def _vault_binary_path(self, rel: str, allowed_ext: tuple) -> pathlib.Path:
    """Resolve `rel` under the vault for binary files. Mirrors
    _vault_resolve but allows the caller's extension instead of forcing
    .md. Used by export/generate endpoints to drop files into the vault."""
    if not _vault_root():
        raise ValueError('vault directory not configured')
    root = pathlib.Path(_vault_root()).resolve()
    if not root.is_dir():
        raise ValueError(f'vault directory does not exist: {root}')
    rel = (rel or '').lstrip('/').replace('\\', '/').strip()
    if not rel:
        raise ValueError('path required')
    # Before the extension check and before any mkdir: a dotted segment is a
    # deliverable about to be rendered into a folder no listing will ever
    # show — a success receipt over a file that just left every list the
    # Library keeps. Same sentence as the write doors (#140), so a coworker's
    # EXPORT_* tool and the boss's own save hear the same refusal. `..` is
    # NOT hidden — it falls through to the escape check below, which refuses
    # it as the traversal it is.
    hidden = _vault_hidden_part(rel)
    if hidden:
        raise ValueError(
            'hidden files are not accepted — the Library never lists '
            f'anything under "{hidden}". Drop the leading dot to file '
            'this where it can be seen.')
    ext = pathlib.Path(rel).suffix.lower()
    if ext not in allowed_ext:
        # If no extension was given, append the first allowed one.
        if not ext:
            rel = rel + allowed_ext[0]
            ext = allowed_ext[0]
        else:
            raise ValueError(f'extension must be one of {allowed_ext}, got {ext}')
    candidate = (root / rel).resolve()
    try: candidate.relative_to(root)
    except ValueError: raise ValueError('path escapes vault directory')
    candidate.parent.mkdir(parents=True, exist_ok=True)
    return candidate

def _read_json_body(self):
    length = int(self.headers.get('content-length', 0) or 0)
    try:
        return json.loads(self.rfile.read(length).decode('utf-8') or '{}')
    except json.JSONDecodeError:
        return None

def _export_pptx(self):
    """Render a markdown outline into a real .pptx and save to vault.
    Body: { path, content }. The outline uses `## Slide N: Title` headers
    and bullet lists; each `##` becomes a slide. Requires python-pptx."""
    body = self._read_json_body()
    if body is None: return self._send_json(400, {'error': 'bad json'})
    rel = (body.get('path') or '').strip()
    content = body.get('content') or ''
    if not rel or not content.strip():
        return self._send_json(400, {'error': 'path and content required'})
    try:
        out_path = self._vault_binary_path(rel, ('.pptx',))
    except ValueError as e:
        return self._send_json(400, {'error': str(e)})
    try:
        from pptx import Presentation  # noqa: PLC0415
        from pptx.util import Inches, Pt  # noqa: PLC0415
    except ImportError:
        return self._send_json(503, {'error': 'python-pptx not installed — run: pip install python-pptx'})

    prs = Presentation()
    # Title slide from first H1 if any.
    lines = content.splitlines()
    title_line = next((l for l in lines if l.strip().startswith('# ')), None)
    if title_line:
        layout = prs.slide_layouts[0]
        slide = prs.slides.add_slide(layout)
        slide.shapes.title.text = title_line.lstrip('#').strip()
    # Each ## section becomes a slide.
    cur_title = None
    cur_bullets = []
    def flush():
        if cur_title is None and not cur_bullets: return
        layout = prs.slide_layouts[1]  # Title + Content
        slide = prs.slides.add_slide(layout)
        slide.shapes.title.text = cur_title or 'Slide'
        tf = slide.placeholders[1].text_frame
        tf.clear()
        for i, b in enumerate(cur_bullets):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.text = b
            p.level = 0
    for ln in lines:
        s = ln.rstrip()
        if s.startswith('## '):
            flush()
            cur_title = s[3:].strip()
            # Strip leading "Slide N:" prefix the agents tend to write.
            cur_title = re.sub(r'^Slide\s*\d+\s*[:\-]\s*', '', cur_title, flags=re.IGNORECASE)
            cur_bullets = []
        elif re.match(r'^\s*[-*•]\s+', s):
            cur_bullets.append(re.sub(r'^\s*[-*•]\s+', '', s))
        elif s.strip() and cur_title is not None:
            # Plain paragraph under a slide → also a bullet.
            cur_bullets.append(s.strip())
    flush()

    try:
        prs.save(str(out_path))
    except Exception as e:
        return self._send_json(500, {'error': f'save failed: {e}'})
    rel_out = str(out_path.relative_to(pathlib.Path(_vault_root()).resolve())).replace('\\', '/')
    return self._send_json(200, {'path': rel_out, 'slides': len(prs.slides)})

def _export_docx(self):
    """Render markdown into a real .docx and save to vault. Body: {path, content}.
    Supports headings (# / ## / ###), bullets (- / *), and paragraphs.
    Requires python-docx."""
    body = self._read_json_body()
    if body is None: return self._send_json(400, {'error': 'bad json'})
    rel = (body.get('path') or '').strip()
    content = body.get('content') or ''
    if not rel or not content.strip():
        return self._send_json(400, {'error': 'path and content required'})
    try:
        out_path = self._vault_binary_path(rel, ('.docx',))
    except ValueError as e:
        return self._send_json(400, {'error': str(e)})
    try:
        from docx import Document  # noqa: PLC0415
    except ImportError:
        return self._send_json(503, {'error': 'python-docx not installed — run: pip install python-docx'})

    doc = Document()
    for ln in content.splitlines():
        s = ln.rstrip()
        if not s.strip():
            continue
        if s.startswith('### '):
            doc.add_heading(s[4:].strip(), level=3)
        elif s.startswith('## '):
            doc.add_heading(s[3:].strip(), level=2)
        elif s.startswith('# '):
            doc.add_heading(s[2:].strip(), level=1)
        elif re.match(r'^\s*[-*•]\s+', s):
            doc.add_paragraph(re.sub(r'^\s*[-*•]\s+', '', s), style='List Bullet')
        elif re.match(r'^\s*\d+\.\s+', s):
            doc.add_paragraph(re.sub(r'^\s*\d+\.\s+', '', s), style='List Number')
        else:
            doc.add_paragraph(s.strip())
    try:
        doc.save(str(out_path))
    except Exception as e:
        return self._send_json(500, {'error': f'save failed: {e}'})
    rel_out = str(out_path.relative_to(pathlib.Path(_vault_root()).resolve())).replace('\\', '/')
    return self._send_json(200, {'path': rel_out})

def _export_pdf(self):
    """Render markdown into a .pdf and save to vault. Body: {path, content}.
    Tries weasyprint (best) → reportlab (fallback). Returns 503 if neither."""
    body = self._read_json_body()
    if body is None: return self._send_json(400, {'error': 'bad json'})
    rel = (body.get('path') or '').strip()
    content = body.get('content') or ''
    if not rel or not content.strip():
        return self._send_json(400, {'error': 'path and content required'})
    try:
        out_path = self._vault_binary_path(rel, ('.pdf',))
    except ValueError as e:
        return self._send_json(400, {'error': str(e)})

    # Path A — weasyprint (real CSS, good typography).
    try:
        import markdown as _md  # noqa: PLC0415
        from weasyprint import HTML as _WeasyHTML  # noqa: PLC0415
        html_body = _md.markdown(content, extensions=['tables', 'fenced_code'])
        full_html = f'<html><head><meta charset="utf-8"><style>body{{font-family:Helvetica,Arial,sans-serif;line-height:1.5;padding:48px;}} h1,h2,h3{{color:#222}} code{{background:#f4f4f4;padding:2px 6px;border-radius:3px}} pre{{background:#f4f4f4;padding:12px;border-radius:6px;overflow-x:auto}}</style></head><body>{html_body}</body></html>'
        _WeasyHTML(string=full_html).write_pdf(str(out_path))
        rel_out = str(out_path.relative_to(pathlib.Path(_vault_root()).resolve())).replace('\\', '/')
        return self._send_json(200, {'path': rel_out, 'renderer': 'weasyprint'})
    except ImportError:
        pass
    except Exception as e:
        sys.stderr.write(f'[export pdf] weasyprint failed: {e}\n')

    # Path B — reportlab (simpler, no CSS, ships with most Pythons via pip).
    try:
        from reportlab.lib.pagesizes import letter  # noqa: PLC0415
        from reportlab.lib.styles import getSampleStyleSheet  # noqa: PLC0415
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer  # noqa: PLC0415
    except ImportError:
        return self._send_json(503, {'error': 'install either weasyprint+markdown OR reportlab — run: pip install weasyprint markdown  (or)  pip install reportlab'})

    doc = SimpleDocTemplate(str(out_path), pagesize=letter, topMargin=48, bottomMargin=48, leftMargin=48, rightMargin=48)
    styles = getSampleStyleSheet()
    story = []
    for ln in content.splitlines():
        s = ln.rstrip()
        if not s.strip():
            story.append(Spacer(1, 6))
            continue
        if s.startswith('# '):
            story.append(Paragraph(s[2:].strip(), styles['Title']))
        elif s.startswith('## '):
            story.append(Paragraph(s[3:].strip(), styles['Heading2']))
        elif s.startswith('### '):
            story.append(Paragraph(s[4:].strip(), styles['Heading3']))
        elif re.match(r'^\s*[-*•]\s+', s):
            story.append(Paragraph('• ' + re.sub(r'^\s*[-*•]\s+', '', s), styles['BodyText']))
        else:
            story.append(Paragraph(s.strip(), styles['BodyText']))
    try:
        doc.build(story)
    except Exception as e:
        return self._send_json(500, {'error': f'pdf build: {e}'})
    rel_out = str(out_path.relative_to(pathlib.Path(_vault_root()).resolve())).replace('\\', '/')
    return self._send_json(200, {'path': rel_out, 'renderer': 'reportlab'})

# ---- Image / video generation (user-configured provider) -------------
def _generate_image(self):
    """Generate an image via the user's configured provider, save to vault.
    Body: { path, prompt, provider, model, size?, apiKey? }
    - provider: 'openai' | 'google' | 'fal'
    - apiKey: forwarded from the browser (decrypted client-side); server
      env vars override if set."""
    body = self._read_json_body()
    if body is None: return self._send_json(400, {'error': 'bad json'})
    rel = (body.get('path') or '').strip()
    prompt = (body.get('prompt') or '').strip()
    provider = (body.get('provider') or '').strip().lower()
    model = (body.get('model') or '').strip()
    size = (body.get('size') or '1024x1024').strip()
    if not rel or not prompt or not provider:
        return self._send_json(400, {'error': 'path, prompt, and provider required'})
    try:
        out_path = self._vault_binary_path(rel, ('.png', '.jpg', '.jpeg', '.webp'))
    except ValueError as e:
        return self._send_json(400, {'error': str(e)})

    api_key = body.get('apiKey') or ''
    if provider == 'openai':
        api_key = os.environ.get('OPENAI_API_KEY') or api_key
        if not api_key: return self._send_json(400, {'error': 'OPENAI_API_KEY required'})
        payload = {'model': model or 'dall-e-3', 'prompt': prompt, 'size': size, 'n': 1, 'response_format': 'b64_json'}
        try:
            req = urllib.request.Request('https://api.openai.com/v1/images/generations',
                data=json.dumps(payload).encode('utf-8'),
                headers={'authorization': f'Bearer {api_key}', 'content-type': 'application/json'})
            with urllib.request.urlopen(req, timeout=120) as r:
                j = json.loads(r.read().decode('utf-8'))
            b64 = j.get('data', [{}])[0].get('b64_json', '')
            if not b64: return self._send_json(502, {'error': 'no image returned'})
            out_path.write_bytes(base64.b64decode(b64))
        except urllib.error.HTTPError as e:
            return self._send_json(e.code, {'error': e.read().decode('utf-8', 'replace')[:600]})
        except Exception as e:
            return self._send_json(500, {'error': str(e)})
    elif provider == 'google':
        api_key = os.environ.get('GOOGLE_API_KEY') or api_key
        if not api_key: return self._send_json(400, {'error': 'GOOGLE_API_KEY required'})
        model_id = model or 'gemini-2.5-flash-image-preview'
        # Two flavors of Google image gen:
        #  - Imagen (imagen-3.0-*, imagen-4-*) → :predict endpoint, predictions[].bytesBase64Encoded
        #  - Gemini Flash Image / "nano banana" (gemini-*-image-*) → :generateContent,
        #    candidates[0].content.parts[*].inlineData.data
        # We pick the right endpoint based on the model name so the same
        # GOOGLE_API_KEY works for both — no extra setting required.
        is_gemini = 'gemini' in model_id.lower()
        try:
            if is_gemini:
                url = f'https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={api_key}'
                payload = {
                    'contents': [{'parts': [{'text': prompt}]}],
                    'generationConfig': {'responseModalities': ['IMAGE']},
                }
                req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'),
                    headers={'content-type': 'application/json'})
                with urllib.request.urlopen(req, timeout=180) as r:
                    j = json.loads(r.read().decode('utf-8'))
                b64 = ''
                mime = ''
                cands = j.get('candidates') or []
                if cands:
                    for part in (cands[0].get('content', {}).get('parts') or []):
                        inline = part.get('inlineData') or part.get('inline_data') or {}
                        if inline.get('data'):
                            b64 = inline['data']
                            mime = (inline.get('mimeType') or inline.get('mime_type') or '').lower()
                            break
                if not b64:
                    # Surface text fallback if model returned a refusal instead of image bytes
                    text_out = ''
                    for c in cands:
                        for p in (c.get('content', {}).get('parts') or []):
                            if p.get('text'): text_out += p['text']
                    return self._send_json(502, {'error': f'no image bytes in Gemini response{": " + text_out[:200] if text_out else ""}'})
                out_path.write_bytes(base64.b64decode(b64))
            else:
                url = f'https://generativelanguage.googleapis.com/v1beta/models/{model_id}:predict?key={api_key}'
                payload = {'instances': [{'prompt': prompt}], 'parameters': {'sampleCount': 1}}
                req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'),
                    headers={'content-type': 'application/json'})
                with urllib.request.urlopen(req, timeout=120) as r:
                    j = json.loads(r.read().decode('utf-8'))
                preds = j.get('predictions', [])
                if not preds: return self._send_json(502, {'error': 'no image returned'})
                b64 = preds[0].get('bytesBase64Encoded') or preds[0].get('image', {}).get('bytesBase64Encoded') or ''
                if not b64: return self._send_json(502, {'error': 'no image bytes in response'})
                out_path.write_bytes(base64.b64decode(b64))
        except urllib.error.HTTPError as e:
            return self._send_json(e.code, {'error': e.read().decode('utf-8', 'replace')[:600]})
        except Exception as e:
            return self._send_json(500, {'error': str(e)})
    elif provider == 'fal':
        api_key = os.environ.get('FAL_KEY') or api_key
        if not api_key: return self._send_json(400, {'error': 'FAL_KEY required'})
        model_id = model or 'fal-ai/flux/schnell'
        try:
            req = urllib.request.Request(f'https://fal.run/{model_id}',
                data=json.dumps({'prompt': prompt}).encode('utf-8'),
                headers={'authorization': f'Key {api_key}', 'content-type': 'application/json'})
            with urllib.request.urlopen(req, timeout=180) as r:
                j = json.loads(r.read().decode('utf-8'))
            img_url = ((j.get('images') or [{}])[0]).get('url')
            if not img_url: return self._send_json(502, {'error': 'no image url in fal response'})
            with urllib.request.urlopen(img_url, timeout=60) as img:
                out_path.write_bytes(img.read())
        except urllib.error.HTTPError as e:
            return self._send_json(e.code, {'error': e.read().decode('utf-8', 'replace')[:600]})
        except Exception as e:
            return self._send_json(500, {'error': str(e)})
    elif provider == 'a1111':
        # Automatic1111 Stable Diffusion WebUI — REST API at /sdapi/v1/txt2img.
        # Run A1111 with --api (or --api --listen for LAN). No API key needed.
        base = (body.get('baseUrl') or 'http://127.0.0.1:7860').rstrip('/')
        try:
            w, h = (int(x) for x in size.split('x')[:2]) if 'x' in size else (1024, 1024)
        except Exception:
            w, h = 1024, 1024
        payload = {
            'prompt': prompt,
            'width': w, 'height': h,
            'steps': int(body.get('steps') or 25),
            'cfg_scale': float(body.get('cfgScale') or 7.5),
            'sampler_name': body.get('sampler') or 'DPM++ 2M Karras',
        }
        if model: payload['override_settings'] = {'sd_model_checkpoint': model}
        try:
            req = urllib.request.Request(f'{base}/sdapi/v1/txt2img',
                data=json.dumps(payload).encode('utf-8'),
                headers={'content-type': 'application/json'})
            with urllib.request.urlopen(req, timeout=300) as r:
                j = json.loads(r.read().decode('utf-8'))
            imgs = j.get('images') or []
            if not imgs: return self._send_json(502, {'error': 'no images in A1111 response'})
            out_path.write_bytes(base64.b64decode(imgs[0]))
        except urllib.error.URLError as e:
            return self._send_json(502, {'error': f'A1111 not reachable at {base} — start it with --api flag: {e}'})
        except Exception as e:
            return self._send_json(500, {'error': f'A1111: {e}'})
    elif provider == 'comfyui':
        # ComfyUI — accepts a `workflow` JSON OR a simple `prompt` that we
        # wrap into a minimal txt2img graph. Polls /history for completion
        # then downloads the image bytes from /view.
        base = (body.get('baseUrl') or 'http://127.0.0.1:8188').rstrip('/')
        workflow = body.get('workflow')
        if not workflow:
            # Default minimal txt2img workflow — assumes a SD1.5/SDXL ckpt is
            # loaded under the name in `model` (or "model.safetensors").
            ckpt = model or 'model.safetensors'
            try:
                w, h = (int(x) for x in size.split('x')[:2]) if 'x' in size else (1024, 1024)
            except Exception:
                w, h = 1024, 1024
            workflow = {
                "3": {"class_type": "KSampler", "inputs": {"seed": secrets.randbits(31),
                      "steps": int(body.get('steps') or 25), "cfg": float(body.get('cfgScale') or 7.5),
                      "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0,
                      "model": ["4", 0], "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["5", 0]}},
                "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt}},
                "5": {"class_type": "EmptyLatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}},
                "6": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["4", 1]}},
                "7": {"class_type": "CLIPTextEncode", "inputs": {"text": body.get('negative') or '', "clip": ["4", 1]}},
                "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
                "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "cafresohq", "images": ["8", 0]}},
            }
        client_id = uuid.uuid4().hex
        try:
            # Queue the prompt.
            req = urllib.request.Request(f'{base}/prompt',
                data=json.dumps({'prompt': workflow, 'client_id': client_id}).encode('utf-8'),
                headers={'content-type': 'application/json'})
            with urllib.request.urlopen(req, timeout=30) as r:
                j = json.loads(r.read().decode('utf-8'))
            prompt_id = j.get('prompt_id')
            if not prompt_id: return self._send_json(502, {'error': 'no prompt_id in ComfyUI response'})
            # Poll history until done (max ~5 min).
            hist = None
            for _i in range(150):
                time.sleep(2)
                try:
                    with urllib.request.urlopen(f'{base}/history/{prompt_id}', timeout=10) as r:
                        h = json.loads(r.read().decode('utf-8'))
                    if h.get(prompt_id):
                        hist = h[prompt_id]
                        break
                except Exception:
                    continue
            if not hist: return self._send_json(504, {'error': 'ComfyUI: prompt did not complete within 5 minutes'})
            # Find first image output.
            outputs = hist.get('outputs') or {}
            img_meta = None
            for _node_id, node_out in outputs.items():
                if node_out.get('images'):
                    img_meta = node_out['images'][0]
                    break
            if not img_meta: return self._send_json(502, {'error': 'ComfyUI: no image in outputs'})
            # Download the image bytes.
            qs = urllib.parse.urlencode({k: v for k, v in img_meta.items() if k in ('filename','subfolder','type')})
            with urllib.request.urlopen(f'{base}/view?{qs}', timeout=60) as img:
                out_path.write_bytes(img.read())
        except urllib.error.URLError as e:
            return self._send_json(502, {'error': f'ComfyUI not reachable at {base}: {e}'})
        except Exception as e:
            return self._send_json(500, {'error': f'ComfyUI: {e}'})
    else:
        return self._send_json(400, {'error': f'unsupported provider: {provider}'})
    rel_out = str(out_path.relative_to(pathlib.Path(_vault_root()).resolve())).replace('\\', '/')
    return self._send_json(200, {'path': rel_out, 'provider': provider, 'model': model})

def _generate_video(self):
    """Generate a video via the user's configured provider, save to vault.
    Body: { path, prompt, provider, model, duration?, apiKey? }
    Most video APIs are long-running — this endpoint kicks off the job,
    polls for completion, then writes the bytes. Times out after 10min."""
    body = self._read_json_body()
    if body is None: return self._send_json(400, {'error': 'bad json'})
    rel = (body.get('path') or '').strip()
    prompt = (body.get('prompt') or '').strip()
    provider = (body.get('provider') or '').strip().lower()
    model = (body.get('model') or '').strip()
    duration = int(body.get('duration') or 5)
    if not rel or not prompt or not provider:
        return self._send_json(400, {'error': 'path, prompt, and provider required'})
    try:
        out_path = self._vault_binary_path(rel, ('.mp4', '.mov', '.webm'))
    except ValueError as e:
        return self._send_json(400, {'error': str(e)})

    api_key = body.get('apiKey') or ''
    if provider == 'fal':
        api_key = os.environ.get('FAL_KEY') or api_key
        if not api_key: return self._send_json(400, {'error': 'FAL_KEY required'})
        model_id = model or 'fal-ai/bytedance/seedance/v1/lite/text-to-video'
        try:
            req = urllib.request.Request(f'https://fal.run/{model_id}',
                data=json.dumps({'prompt': prompt, 'duration': duration}).encode('utf-8'),
                headers={'authorization': f'Key {api_key}', 'content-type': 'application/json'})
            with urllib.request.urlopen(req, timeout=600) as r:
                j = json.loads(r.read().decode('utf-8'))
            video_url = (j.get('video') or {}).get('url') or j.get('url') or ''
            if not video_url: return self._send_json(502, {'error': 'no video url in fal response'})
            with urllib.request.urlopen(video_url, timeout=300) as vid:
                out_path.write_bytes(vid.read())
        except urllib.error.HTTPError as e:
            return self._send_json(e.code, {'error': e.read().decode('utf-8', 'replace')[:600]})
        except Exception as e:
            return self._send_json(500, {'error': str(e)})
    elif provider == 'openai':
        # Sora API is gated; we provide the call shape but most accounts
        # will get a 403. The error message guides the user.
        api_key = os.environ.get('OPENAI_API_KEY') or api_key
        if not api_key: return self._send_json(400, {'error': 'OPENAI_API_KEY required'})
        return self._send_json(501, {'error': 'OpenAI Sora video generation not yet wired (API still gated). Try provider=fal with a Seedance/Veo model instead.'})
    elif provider == 'google':
        return self._send_json(501, {'error': 'Google Veo direct API not yet wired. Try provider=fal with a Veo model instead.'})
    elif provider == 'comfyui':
        # ComfyUI for video — caller passes a `workflow` JSON describing
        # an AnimateDiff / SVD / Hunyuan / Mochi graph. We don't synthesize
        # a default one because video workflows are model-specific.
        base = (body.get('baseUrl') or 'http://127.0.0.1:8188').rstrip('/')
        workflow = body.get('workflow')
        if not workflow:
            return self._send_json(400, {
                'error': 'ComfyUI video requires a `workflow` JSON (export from your AnimateDiff/SVD/Mochi/Hunyuan setup). Auto-default not provided because video workflows are model-specific. See docs.'
            })
        client_id = uuid.uuid4().hex
        try:
            req = urllib.request.Request(f'{base}/prompt',
                data=json.dumps({'prompt': workflow, 'client_id': client_id}).encode('utf-8'),
                headers={'content-type': 'application/json'})
            with urllib.request.urlopen(req, timeout=30) as r:
                j = json.loads(r.read().decode('utf-8'))
            prompt_id = j.get('prompt_id')
            if not prompt_id: return self._send_json(502, {'error': 'no prompt_id in ComfyUI response'})
            hist = None
            for _i in range(300):  # video takes longer — up to ~10 min
                time.sleep(2)
                try:
                    with urllib.request.urlopen(f'{base}/history/{prompt_id}', timeout=10) as r:
                        h = json.loads(r.read().decode('utf-8'))
                    if h.get(prompt_id):
                        hist = h[prompt_id]
                        break
                except Exception:
                    continue
            if not hist: return self._send_json(504, {'error': 'ComfyUI: prompt did not complete within 10 minutes'})
            outputs = hist.get('outputs') or {}
            # Look for video output — VHS_VideoCombine, SaveVideo, etc.
            vid_meta = None
            for _node_id, node_out in outputs.items():
                for key in ('videos', 'gifs', 'images'):  # some nodes call the file 'images' even for mp4
                    if node_out.get(key):
                        vid_meta = node_out[key][0]
                        break
                if vid_meta: break
            if not vid_meta: return self._send_json(502, {'error': 'ComfyUI: no video in outputs — does your workflow include VHS_VideoCombine or SaveVideo?'})
            qs = urllib.parse.urlencode({k: v for k, v in vid_meta.items() if k in ('filename','subfolder','type')})
            with urllib.request.urlopen(f'{base}/view?{qs}', timeout=300) as vid:
                out_path.write_bytes(vid.read())
        except urllib.error.URLError as e:
            return self._send_json(502, {'error': f'ComfyUI not reachable at {base}: {e}'})
        except Exception as e:
            return self._send_json(500, {'error': f'ComfyUI: {e}'})
    else:
        return self._send_json(400, {'error': f'unsupported provider: {provider}'})
    rel_out = str(out_path.relative_to(pathlib.Path(_vault_root()).resolve())).replace('\\', '/')
    return self._send_json(200, {'path': rel_out, 'provider': provider, 'model': model})
