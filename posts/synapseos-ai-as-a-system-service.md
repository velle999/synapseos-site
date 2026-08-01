---
title: I built a Linux distro where the AI is a system service, not an app
slug: synapseos-ai-as-a-system-service
subtitle: SynapseOS puts a local LLM daemon at the system layer and lets the shell, the compositor, the security monitor and a kernel module talk to it over a Unix socket.
tags: linux, artificial-intelligence, opensource, llm, wayland
cover: /public/assets/synui-desktop.png
seoTitle: SynapseOS — an Arch-based Linux distro with a local LLM in the system layer
seoDescription: SynapseOS runs a local LLM as a system service. An AI-native shell, a wlroots compositor, a security monitor with in-kernel enforcement, and a DKMS kernel module — all talking to one inference daemon. No cloud, no API keys.
ogImage: https://synapseos.pages.dev/assets/og.png
enableToc: true
---

Most "AI operating systems" are a chat window on a normal desktop. You install a
thing, you open the thing, you talk to the thing, you close the thing. The
operating system underneath is unchanged and doesn't know the model exists.

I wanted to know what happens if you start one layer down — if the model is a
system service in the same sense that `systemd-resolved` is. Something the rest
of the OS can *depend on* rather than an app you open.

That's [SynapseOS](https://synapseos.pages.dev/). It's an Arch-based
distribution, it's at 0.2.6, it's alpha, and I daily-drive it.

## The shape of it

One daemon owns the model. `synapd` loads a GGUF through llama.cpp and serves
every other component over a Unix socket:

```
  User
   │
   ▼
 synsh ─── natural language / commands ──┐
   │                                     │
   ▼                                     │
 synapd  (local LLM — Mistral 7B)        │
   │  inference over SYN socket protocol │
   ├──► synguard      security verdicts ─┤
   ├──► synnet        network policy     │
   └──► synapse_kmod  kernel sysfs       │
            │                            ▼
            ▼                    synui (Wayland)
     /sys/kernel/synapse/
     syscall_log, ai_hints, stats,
     status, config, version
```

The important word there is *one*. Every component queries the model that is
already resident — the AI coding assistant doesn't load a second copy and spend
another 4 GB of VRAM to answer a question the daemon three processes over could
have answered. That constraint drove more of the architecture than anything else.

The pieces:

- **`synapd`** — the inference daemon. Owns the model, drops root after start.
- **`synsh`** — a shell. It's a normal shell until you stop typing commands and
  start describing outcomes; then it resolves intent against the local model and
  shows you what it's about to run before it runs it.
- **`synui`** — a Wayland compositor on wlroots 0.20, rendering through scenefx
  0.5. Tiling and monocle layouts, per-output workspaces, XWayland, layer-shell,
  glass, blur, shadows, and an optional CRT post-process pass because I wanted
  one.
- **`synguard`** — a security monitor. Classifies syscall events, scores threats,
  publishes verdicts on a feed the compositor subscribes to.
- **`synnet`** — network policy with nftables.
- **`synapse_kmod`** — a DKMS kernel module exporting syscall telemetry and
  scheduling hints through `/sys/kernel/synapse/`.

Nothing leaves the machine. The ISO embeds Mistral 7B Instruct (Q4_K_M, ~4.1 GB),
so the AI is live on first boot with the network cable out. There are no API keys
to configure because there is nothing to configure them for.

## What "AI in the system layer" actually buys you

The honest answer is: it depends on the component, and it's more interesting in
some than others.

**The shell** is the obvious one and the least surprising. Natural language in,
a command out, confirm before it runs. Useful, not novel.

**The security monitor** is where it started paying rent. `synguard` sees a
firehose of syscall events; the hard part was never *collecting* them, it was
deciding which forty of the nine thousand events since boot are worth waking a
human for. Having a local model to classify them changes what's affordable —
you can afford to ask a question about an event when asking costs you nothing
and tells no one.

That path went further in 0.2.4: `synguard` stopped being detect-only and got a
BPF-LSM gate that returns `-EPERM` in-kernel. It's opt-in, and it's wrapped in
warmup, a dead-man heartbeat and a deny budget, because a security daemon that
can deny syscalls is one bug away from being the most effective piece of malware
on the system. Fail-open is deliberate everywhere.

**The compositor** holds a live subscription to that verdict feed. `Super`+`A`
opens a neural activity overlay showing what the daemon is doing. This is the
part I'm least done with.

## The desktop is not a reskin

`synui` is written for this system rather than adapted to it. It draws its own
display settings, wallpaper picker, dock, cursor picker, sound panel and control
panel — there's no third-party settings app in the picture. The status bar and
desktop widgets are a native [quickshell](https://quickshell.org/) shell;
waybar was in there for a long time and got replaced.

0.2.6 was mostly about the desktop growing up. Fifteen compositor-drawn panels
were keyboard-only — they said "Up/Down select · Enter activate" and meant it
literally, and none of them closed when you clicked off, which is the one thing
every menu on every desktop does. They now work under one contract: hover
selects, left click does the row's primary action, a click off closes, the wheel
scrolls. Every click routes through the panel's own activate path, so the mouse
and the keyboard can't come to disagree about what a row does.

The deliberate exceptions are all about not doing something destructive by
accident. The task manager's click only *selects* — kill stays on the keyboard.
The wallpaper and cursor pickers take a double click, because moving their
selection applies a wallpaper.

## Two bugs worth the reading time

Building a distro means most of your bugs are in the *build*, and the build is
the one thing you can't test by running it.

**The CPU ISO that was secretly linking CUDA.** The llama.cpp build directory is
reused between runs to avoid a 20-minute recompile, which means `CMakeCache.txt`
survives — and CMake `option()` values are sticky. A toggle you don't pass with
`-D` keeps whatever the cache says. The CPU path set `GGML_NATIVE=OFF` and never
mentioned `GGML_CUDA` at all, so a cache left behind by an earlier CUDA build
kept `GGML_CUDA=ON`. The log printed `CMake configure (GPU: cpu)` and then
`Including CUDA backend` three lines later.

The result would have been an ISO whose inference daemon links `libcuda.so.1`
and therefore fails to start on every machine without an NVIDIA driver — the
headline feature dead everywhere except the machine that built it. Every backend
toggle is now stated explicitly on every path, and the backends build in separate
directories so it's structurally impossible rather than merely fixed.

**The update system that couldn't.** Every installed SynapseOS got a
`[synapseos]` pacman repository pointing at a directory copied off the ISO at
install time — which nothing ever wrote to again. `pacman -Syu` would upgrade all
of Arch and could never see a newer `synui`, `synapd` or `synguard`. **With no
error.** An installed system was frozen at whatever ISO installed it, and it
looked completely healthy.

That's the failure mode I've learned to fear most in this project: not the crash,
but the thing that succeeds at doing nothing. `syn-update` shipped in 0.2.3 and
is the first time an installed system could move at all.

## Try it, carefully

It's alpha. Version 0.2.x. It moves fast and it will break — run it in a VM
before you give it a disk. The ISO is ~7.9 GB (the model is most of that) and
GitHub's 2 GiB asset cap means it's split into parts you reassemble:

```sh
cat SynapseOS-0.2.6-x86_64.iso.part* > SynapseOS-0.2.6-x86_64.iso
sha256sum -c SynapseOS-0.2.6-x86_64.iso.sha256
```

Or skip the USB stick entirely:

```sh
git clone https://github.com/velle999/SYNAPSE.git && cd SYNAPSE
QEMU_RAM=8G ./archiso/build_scripts/qemu-test.sh
```

You want 8 GB of RAM or more — the 7B model is the reason. A GPU is optional;
CPU inference is the default and works everywhere, with CUDA and Vulkan builds
available afterward if you have the hardware.

When you're ready to install for real, `syn-install` does a whole-disk install
with optional LUKS2 full-disk encryption, or a non-destructive UEFI dual-boot
into existing free space, reusing the machine's ESP.

- **Site:** [synapseos.pages.dev](https://synapseos.pages.dev/)
- **Source:** [github.com/velle999/SYNAPSE](https://github.com/velle999/SYNAPSE)
- **Download:** [latest release](https://github.com/velle999/SYNAPSE/releases/latest)

GPL-2.0-or-later, except the kernel module, which is GPL-2.0-only because the
Linux kernel is.

If you try it, I want the bug reports — especially from hardware I don't own,
which is most hardware.
