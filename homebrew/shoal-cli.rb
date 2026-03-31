# typed: false
# frozen_string_literal: true

class ShoalCli < Formula
  desc "Terminal-first orchestration tool for parallel AI coding agents"
  homepage "https://github.com/TheShoal/shoal-cli"
  license "MIT"
  version "0.27.0"

  on_macos do
    if Hardware::CPU.arm?
      url "https://github.com/TheShoal/shoal-cli/releases/download/v#{version}/shoal-darwin-arm64"
      sha256 "PLACEHOLDER"

      def install
        bin.install "shoal-darwin-arm64" => "shoal"
      end
    elsif Hardware::CPU.intel?
      url "https://github.com/TheShoal/shoal-cli/releases/download/v#{version}/shoal-darwin-x86_64"
      sha256 "PLACEHOLDER"

      def install
        bin.install "shoal-darwin-x86_64" => "shoal"
      end
    end
  end

  depends_on "tmux"
  depends_on "git"
  depends_on "fzf" => :recommended
  depends_on "fish" => :optional

  test do
    assert_match version.to_s, shell_output("#{bin}/shoal --version")
  end
end
