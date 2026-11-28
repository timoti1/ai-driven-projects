# video-editing -- one episode per directory, one command per pipeline step.
#
#   make venv       create .venv and install the python dependencies
#   make deps       check the system packages (ffmpeg+VAAPI, tesseract) are there
#   make dirs       create source/ work/ edit/ render/ logs/
#   make init       dirs + copy the example style and topic map into edit/
#   make download ID=<youtube id>
#   make analyze    transcript, silence, loudness, motion, slides
#   make plan       cut plan + panel visibility gates (reads edit/topics.json)
#   make check      audit_titles + probe_dashboard: both must PASS before a render
#   make audio      audio track cut to match the video cuts
#   make plate      rebuild the dashboard plate PNG (after any style.json change)
#   make test       render a short piece and verify it
#   make render     cards + body + concat  ->  render/final.mp4
#   make verify     measure the finished file against the plan
#   make episode    everything above, in order
#
# The scripts derive their root from __file__, so the tree works wherever it is
# cloned; everything below is relative to this Makefile.

V    := $(CURDIR)
PY   := $(V)/.venv/bin/python
PIP  := $(V)/.venv/bin/pip
ID   ?=
SRC  := $(V)/source/$(ID).mp4

.PHONY: venv deps dirs init download analyze plan check audio plate test render verify episode

venv:
	python3 -m venv $(V)/.venv
	$(PIP) install --upgrade pip
	$(PIP) install -r $(V)/requirements.txt

deps:
	@echo "system packages needed (apt):"
	@echo "  sudo apt-get install ffmpeg tesseract-ocr tesseract-ocr-rus"
	@command -v ffmpeg >/dev/null || { echo "  ffmpeg: MISSING"; exit 0; }
	@ffmpeg -hide_banner -encoders 2>/dev/null | grep -q vaapi \
		&& echo "  ffmpeg: present, VAAPI available (GPU encode possible)" \
		|| echo "  ffmpeg: present, no VAAPI -> set encoder=libx264 in edit/style.json"
	@command -v tesseract >/dev/null && tesseract --list-langs 2>/dev/null | grep -qx rus \
		&& echo "  tesseract: present with rus" || echo "  tesseract: missing rus -> probe/verify cannot run"
	@$(PY) -c "import numpy,PIL,fontTools,pymorphy3" 2>/dev/null \
		&& echo "  python deps: ok" || echo "  python deps: missing -> run make venv"
	@command -v $(V)/.venv/bin/yt-dlp >/dev/null && $(V)/.venv/bin/yt-dlp --version | sed 's/^/  yt-dlp: /' || true

dirs:
	mkdir -p $(V)/source $(V)/work $(V)/edit $(V)/render $(V)/logs

init: dirs
	@[ -f $(V)/edit/style.json ] || cp $(V)/config/style.example.json $(V)/edit/style.json
	@[ -f $(V)/edit/topics.json ] || cp $(V)/config/topics.example.json $(V)/edit/topics.json
	@echo "edit/ ready. Now rewrite edit/topics.json for this episode (video_id," \
	      "channel, lesson, topics[]); leave edit/style.json alone unless the series" \
	      "look must change."

download:
	@test -n "$(ID)" || { echo "usage: make download ID=<youtube id>"; exit 1; }
	$(V)/.venv/bin/yt-dlp -4 -f "bv[ext=mp4][height=1080]+ba[ext=m4a]/b" \
		--merge-output-format mp4 --write-info-json --write-subs --write-auto-subs \
		--sub-langs "ru,*.ru" -o "$(V)/source/%(id)s.%(ext)s" \
		"https://www.youtube.com/watch?v=$(ID)"

analyze:
	@test -n "$(ID)" || { echo "usage: make analyze ID=<youtube id>"; exit 1; }
	@if [ -f $(V)/source/$(ID).ru.vtt ] || [ -f $(V)/source/$(ID).ru-orig.vtt ]; then \
		for f in $(V)/source/$(ID).ru.vtt $(V)/source/$(ID).ru-orig.vtt; do \
			[ -f $$f ] && $(PY) $(V)/scripts/parse_vtt.py $$f $(V)/work/speech.json && break; done; \
	else echo "no captions: extract audio and run transcribe.py"; \
		ffmpeg -y -v error -i $(SRC) -vn -ac 1 -ar 16000 $(V)/source/$(ID).wav; \
		$(PY) $(V)/scripts/transcribe.py $(V)/source/$(ID).wav $(V)/work/speech.json; fi
	$(PY) $(V)/scripts/analyze_audio.py $(SRC) $(V)/work
	$(PY) $(V)/scripts/detect_hum.py $(SRC) $(V)/work/hum.json
	$(PY) $(V)/scripts/analyze_motion.py $(SRC) $(V)/work
	$(PY) $(V)/scripts/extract_slides.py $(SRC) $(V)/work/slides.json
	ffmpeg -nostats -v info -i $(SRC) -vn \
		-af silencedetect=noise=-35dB:d=0.17 -f null - 2> $(V)/work/silence_raw.txt

plan:
	$(PY) $(V)/scripts/build_plan.py
	$(PY) $(V)/scripts/panel_gates.py

check:
	$(PY) $(V)/scripts/audit_titles.py
	$(PY) $(V)/scripts/probe_dashboard.py

audio:
	$(PY) $(V)/scripts/cut_audio.py

plate:
	$(PY) $(V)/scripts/make_plate.py

test: plate
	$(PY) $(V)/scripts/render.py --test 120

render: plate
	$(PY) $(V)/scripts/render.py

verify:
	$(PY) $(V)/scripts/verify_output.py $(V)/render/final.mp4

episode: analyze plan check audio test render verify
