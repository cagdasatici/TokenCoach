class Tokencoach < Formula
  desc "Menu bar coach for what Claude and ChatGPT prompts cost and how to spend less"
  homepage "https://github.com/cagdasatici/TokenCoach"
  url "https://github.com/cagdasatici/TokenCoach/releases/download/v1.1.0/TokenCoach-1.1.0.tar.gz"
  sha256 "51ae228067ade31058aed01a7b662161c34c17139ea570e47f9eeaeb6486094d"
  license "MIT"
  head "https://github.com/cagdasatici/TokenCoach.git", branch: "main"

  depends_on :macos
  depends_on "python@3.12"

  def install
    venv = libexec/"venv"
    system Formula["python@3.12"].opt_bin/"python3.12", "-m", "venv", venv

    # pyobjc-core reads $HOME during build; point it at a writable dir
    ENV["HOME"] = buildpath

    # Install from requirements.txt rather than pinned sdist resources:
    # curl-cffi's sdist runs a build script that writes to a hardcoded path
    # and fails, while its published wheels install cleanly.
    system venv/"bin/pip", "install", "--upgrade", "pip"
    system venv/"bin/pip", "install", "-r", "requirements.txt"

    libexec.install "tokencoach.py", "tokencoach_nudge.py", "tokencoach", "assets"

    # rumps notifications need a bundle identifier next to the interpreter
    system "/usr/libexec/PlistBuddy", "-c",
           "Add :CFBundleIdentifier string io.github.cagdasatici.tokencoach", (venv/"bin/Info.plist").to_s

    # Launch through opt_libexec, a path that survives `brew upgrade`, so the
    # login agent and the Claude Code hook keep working after upgrades.
    (bin/"tokencoach").write <<~SH
      #!/bin/bash
      exec "#{opt_libexec}/venv/bin/python" "#{opt_libexec}/tokencoach.py" "$@"
    SH
  end

  def caveats
    <<~EOS
      Start TokenCoach once; it adds itself to your login items:
        tokencoach &

      Then click the ◆ in your menu bar → Open dashboard.

      Try it with sample data first (nothing of yours is read):
        tokencoach --demo

      The optional desktop widget needs Xcode; use the one-line installer
      from the README if you want it.

      Before `brew uninstall tokencoach`, run `tokencoach --cleanup` to remove
      its login item and Claude Code hook.

      Upgrading from 1.1.0: run `tokencoach &` once, so it can repair the
      login item that 1.1.0 pointed at the folder this upgrade removed.
    EOS
  end

  test do
    ENV["TOKENCOACH_DATA_DIR"] = testpath/"data"
    system libexec/"venv/bin/python", "-c",
           "import sys; sys.path.insert(0, '#{libexec}'); " \
           "import tokencoach.ledger, tokencoach.coach, tokencoach.ledger_report, tokencoach.server"
  end
end
