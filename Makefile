# Makefile for the Ohlfs font pipeline.
#
#   make             — full pipeline: regenerate sources + build all OTFs
#   make sources     — regenerate glyphs-extras.txt
#   make glyphs      — dump existing Light glyphs + coverage report
#   make bold        — build Ohlfs-Bold.otf from Ohlfs-Light.otf
#   make extra       — build Ohlfs-Extra.otf + Ohlfs-Extra-Bold.otf
#   make install     — copy all generated OTFs to ~/Library/Fonts/
#   make uninstall   — remove our OTFs from ~/Library/Fonts/
#   make clean       — delete generated artefacts
#   make verify      — print font name records for all generated OTFs

ROOT      := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
PYTHON    := python3
FONT_DIR  := $(HOME)/Library/Fonts

LIGHT_SRC := $(FONT_DIR)/Ohlfs-Light.otf

# Generators → text sources
EXTRAS_TXT := $(ROOT)/glyphs-extras.txt
GLYPHS_TXT := $(ROOT)/glyphs.txt
MISSING_TXT:= $(ROOT)/missing.txt

# Output OTFs
BOLD_OTF             := $(ROOT)/Ohlfs-Bold.otf
ITALIC_OTF           := $(ROOT)/Ohlfs-Italic.otf
BOLD_ITALIC_OTF      := $(ROOT)/Ohlfs-Bold-Italic.otf
EXTRA_OTF            := $(ROOT)/Ohlfs-Extra.otf
EXTRA_BOLD_OTF       := $(ROOT)/Ohlfs-Extra-Bold.otf
EXTRA_ITALIC_OTF     := $(ROOT)/Ohlfs-Extra-Italic.otf
EXTRA_BOLD_ITALIC_OTF := $(ROOT)/Ohlfs-Extra-Bold-Italic.otf

INSTALLED := $(FONT_DIR)/Ohlfs-Bold.otf \
             $(FONT_DIR)/Ohlfs-Italic.otf \
             $(FONT_DIR)/Ohlfs-Bold-Italic.otf \
             $(FONT_DIR)/Ohlfs-Extra.otf \
             $(FONT_DIR)/Ohlfs-Extra-Bold.otf \
             $(FONT_DIR)/Ohlfs-Extra-Italic.otf \
             $(FONT_DIR)/Ohlfs-Extra-Bold-Italic.otf

.PHONY: all sources glyphs bold italic extra install uninstall clean verify help

all: sources bold italic extra

# ----- Source generation --------------------------------------------------

sources: $(EXTRAS_TXT)

$(EXTRAS_TXT): gen_extras.py
	$(PYTHON) gen_extras.py

# Dump existing Light glyphs as editable bitmaps + coverage report
glyphs: $(GLYPHS_TXT)

$(GLYPHS_TXT) $(MISSING_TXT): dump_glyphs.py $(LIGHT_SRC)
	$(PYTHON) dump_glyphs.py

# ----- Font builds --------------------------------------------------------

bold: $(BOLD_OTF)

$(BOLD_OTF): make_bold.py $(LIGHT_SRC)
	$(PYTHON) make_bold.py

italic: $(ITALIC_OTF) $(BOLD_ITALIC_OTF)

# Both italic OTFs are produced by a single make_italic.py invocation.
$(ITALIC_OTF) $(BOLD_ITALIC_OTF): make_italic.py make_bold.py $(LIGHT_SRC)
	$(PYTHON) make_italic.py

extra: $(EXTRA_OTF) $(EXTRA_BOLD_OTF) $(EXTRA_ITALIC_OTF) $(EXTRA_BOLD_ITALIC_OTF)

# All Extra OTFs are produced by a single build.py invocation.
$(EXTRA_OTF) $(EXTRA_BOLD_OTF) $(EXTRA_ITALIC_OTF) $(EXTRA_BOLD_ITALIC_OTF): build.py make_bold.py make_italic.py $(EXTRAS_TXT) $(LIGHT_SRC)
	$(PYTHON) build.py

# ----- Install ------------------------------------------------------------

install: all
	cp $(BOLD_OTF) $(ITALIC_OTF) $(BOLD_ITALIC_OTF) \
	   $(EXTRA_OTF) $(EXTRA_BOLD_OTF) $(EXTRA_ITALIC_OTF) $(EXTRA_BOLD_ITALIC_OTF) \
	   $(FONT_DIR)/
	@echo "Installed:"
	@ls -la $(INSTALLED)

uninstall:
	@for f in $(INSTALLED); do \
		if [ -f "$$f" ]; then trash "$$f" && echo "removed $$f"; fi \
	done

# ----- Inspection ---------------------------------------------------------

verify:
	@$(PYTHON) -c "from fontTools.ttLib import TTFont; \
	[print(p, '→', TTFont(p)['name'].getBestFamilyName(), '/', \
	       TTFont(p)['name'].getBestSubFamilyName(), \
	       'weight=', TTFont(p)['OS/2'].usWeightClass, \
	       'glyphs=', TTFont(p)['maxp'].numGlyphs) \
	 for p in ['$(BOLD_OTF)', '$(ITALIC_OTF)', '$(BOLD_ITALIC_OTF)', \
	           '$(EXTRA_OTF)', '$(EXTRA_BOLD_OTF)', \
	           '$(EXTRA_ITALIC_OTF)', '$(EXTRA_BOLD_ITALIC_OTF)']]"

# ----- Cleanup ------------------------------------------------------------

clean:
	@for f in $(BOLD_OTF) $(ITALIC_OTF) $(BOLD_ITALIC_OTF) \
	          $(EXTRA_OTF) $(EXTRA_BOLD_OTF) $(EXTRA_ITALIC_OTF) $(EXTRA_BOLD_ITALIC_OTF) \
	          $(EXTRAS_TXT) $(GLYPHS_TXT) $(MISSING_TXT); do \
		if [ -f "$$f" ]; then trash "$$f" && echo "removed $$f"; fi \
	done

help:
	@echo "Targets:"
	@echo "  all (default)  regenerate sources + build all OTFs"
	@echo "  sources        regenerate glyphs-extras.txt"
	@echo "  glyphs         dump existing Light glyphs (glyphs.txt + missing.txt)"
	@echo "  bold           build Ohlfs-Bold.otf"
	@echo "  italic         build Ohlfs-Italic.otf + Ohlfs-Bold-Italic.otf"
	@echo "  extra          build Ohlfs-Extra.otf + Bold + Italic + Bold-Italic"
	@echo "  install        copy generated OTFs to ~/Library/Fonts/"
	@echo "  uninstall      remove generated OTFs from ~/Library/Fonts/"
	@echo "  verify         show name records / glyph counts for built OTFs"
	@echo "  clean          delete generated text + OTF artefacts"
