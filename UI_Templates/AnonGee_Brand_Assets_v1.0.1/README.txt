AnonGee Brand Assets v1.0.1
=============================

Approved brand system package for AnonGee / AnonGee BIM Tools.

Core identity
- Symbol: traced from the approved Concept 3 artwork.
- Wordmark treatment: Doppio One-like geometric sans, SemiBold appearance.
- Anon: Vivid Red #E02020
- Gee: Silver Steel #C0C8D8
- Charcoal Black: #141414
- White: #FFFFFF

Package update
- Fixed the wordmark overlap issue between "Anon" and "Gee" in the lockup assets.
- The symbol remains unchanged.

Important
- One coherent master identity is reused across Setup.exe, Add/Remove Programs, Start Menu, Desktop Shortcut, pyRevit Home/About/Settings, GitHub, documentation, website, splash, and About surfaces.
- Do not redesign the logo per surface. Use the aliases and sizes supplied here.
- The SVG masters declare `Doppio One` first with a fallback. The package does NOT redistribute font files.
- Raster wordmark assets were rendered using a similar installed geometric sans because Doppio One is not bundled in this environment.

Inno Setup
SetupIconFile=assets\anongee-setup.ico
WizardImageFile=assets\wizard\welcome-light.png
WizardImageFileDynamicDark=assets\wizard\welcome-dark.png
WizardSmallImageFile=assets\wizard\small-light.png
WizardSmallImageFileDynamicDark=assets\wizard\small-dark.png

Recommended pyRevit
Use the 32px or 64px transparent PNG symbol for Home/About/Settings pushbuttons; pyRevit can downscale as needed.

Versioning
Package semantic version: 1.0.1
