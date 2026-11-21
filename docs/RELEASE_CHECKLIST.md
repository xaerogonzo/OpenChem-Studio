# Release checklist (by hand, on the DRAFT's installer)

Read by TokenSave Manager's Release Wizard (`release-flow.json`, key `checklist`): one
`- [ ]` line is one item it shows and remembers per tag. The pipeline runs the app; it does
not draw a molecule, and it cannot press a Windows dialog. Download the installer from the
**draft release**, not from a local build, then go through this before pressing Publish.

- [ ] Downloaded the setup .exe from the draft release, not from a local build
- [ ] The install-folder page is always shown (also on a re-run), and Browse > Make New Folder creates a folder
- [ ] Installed per-user, and again for all users (this one asks Windows for permission)
- [ ] The documentation folder and the changelog are installed
- [ ] Start menu entries: the program, Uninstall OpenChem Studio, the documentation, the changelog, the online link
- [ ] Running Setup again over the install asks repair/update, uninstall or cancel
- [ ] Uninstall asks about settings and about caches/tools, both unticked; saved project files are kept
- [ ] Uninstalling ticking neither box then reinstalling keeps settings and tools
- [ ] Double-clicking a .ocsproj file opens it in the app
- [ ] Save and Save As work
- [ ] Windows Defender Controlled Folder Access: if it is on, saving into Documents is blocked until the app is allowed; the message tells the person what to do
- [ ] The 2D editor draws, both 3D viewers render, and a molecule gets a name
- [ ] Help opens and F1 works on a panel
