import React from 'react';
import {
  Sparkles,
  Download,
  Wand2,
  BookOpen,
  ArrowRight,
  Menu,
  Plus,
} from 'lucide-react';
import { FiTwitter, FiLinkedin, FiInstagram } from 'react-icons/fi';

const VIDEO_URL = 'https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260315_073750_51473149-4350-4920-ae24-c8214286f323.mp4';

const SOCIAL_LINKS = {
  twitter: 'https://twitter.com/bloom',
  linkedin: 'https://linkedin.com/company/bloom',
  instagram: 'https://instagram.com/bloom',
};

export const BloomLanding: React.FC = () => {
  return (
    <div className="relative w-screen h-screen overflow-hidden bg-black font-display">
      {/* Video Background */}
      <video
        autoPlay
        loop
        muted
        playsInline
        className="absolute inset-0 w-full h-full object-cover z-0"
      >
        <source src={VIDEO_URL} type="video/mp4" />
      </video>

      {/* Main Layout - Two Panel Split */}
      <div className="relative z-10 flex min-h-screen">
        {/* Left Panel - 52% */}
        <div className="w-full lg:w-[52%] h-screen flex flex-col p-4 lg:p-6">
          {/* Liquid Glass Strong Overlay */}
          <div className="absolute inset-4 lg:inset-6 rounded-[1.5rem] liquid-glass-strong pointer-events-none" />

          {/* Navigation */}
          <nav className="relative z-20 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <img
                src="/logo.png"
                alt="Bloom Logo"
                className="w-8 h-8"
              />
              <span className="text-2xl font-semibold tracking-tight text-white">
                bloom
              </span>
            </div>
            <button
              className="liquid-glass rounded-full px-4 py-2 flex items-center gap-2 text-white text-sm hover:scale-105 transition-transform cursor-pointer"
              aria-label="Open menu"
            >
              <Menu className="w-4 h-4" />
              <span>Menu</span>
            </button>
          </nav>

          {/* Hero Center Content */}
          <div className="flex-1 flex flex-col items-center justify-center relative z-20">
            {/* Hero Logo */}
            <img
              src="/logo.png"
              alt="Bloom Logo"
              className="w-20 h-20 mb-8"
            />

            {/* Hero Headline */}
            <h1 className="text-5xl md:text-6xl lg:text-7xl font-medium tracking-[-0.05em] text-white text-center mb-10 leading-tight">
              Innovating the{' '}
              <em className="font-serif text-white/80 not-italic">
                spirit of bloom
              </em>{' '}
              AI
            </h1>

            {/* CTA Button */}
            <button className="liquid-glass-strong rounded-full px-8 py-4 flex items-center gap-3 text-white mb-10 hover:scale-105 active:scale-95 transition-transform cursor-pointer">
              <span className="text-base font-medium">Explore Now</span>
              <div className="w-7 h-7 rounded-full bg-white/15 flex items-center justify-center">
                <Download className="w-4 h-4" />
              </div>
            </button>

            {/* Feature Pills */}
            <div className="flex flex-wrap justify-center gap-3">
              <span className="liquid-glass rounded-full px-4 py-2 text-xs text-white/80 hover:scale-105 transition-transform cursor-pointer">
                Artistic Gallery
              </span>
              <span className="liquid-glass rounded-full px-4 py-2 text-xs text-white/80 hover:scale-105 transition-transform cursor-pointer">
                AI Generation
              </span>
              <span className="liquid-glass rounded-full px-4 py-2 text-xs text-white/80 hover:scale-105 transition-transform cursor-pointer">
                3D Structures
              </span>
            </div>
          </div>

          {/* Bottom Quote */}
          <div className="relative z-20 text-center mt-auto">
            <p className="text-xs tracking-widest uppercase text-white/50 mb-3">
              VISIONARY DESIGN
            </p>
            <blockquote className="text-lg md:text-xl text-white mb-4 font-display">
              &ldquo;We imagined a realm with{' '}
              <span className="font-serif italic">no ending.</span>&rdquo;
            </blockquote>
            <div className="flex items-center justify-center gap-4">
              <div className="h-px w-12 bg-white/30" />
              <p className="text-sm font-medium tracking-wider text-white/60">
                MARCUS AURELIO
              </p>
              <div className="h-px w-12 bg-white/30" />
            </div>
          </div>
        </div>

        {/* Right Panel - 48% (Desktop Only) */}
        <div className="hidden lg:flex w-[48%] h-screen flex-col p-6 relative z-20">
          {/* Top Bar with Social Links */}
          <div className="flex items-center justify-between">
            <div className="liquid-glass rounded-full px-4 py-2 flex items-center gap-3">
              <a
                href={SOCIAL_LINKS.twitter}
                target="_blank"
                rel="noopener noreferrer"
                className="text-white hover:text-white/80 transition-colors"
                aria-label="Twitter"
              >
                <FiTwitter className="w-4 h-4" />
              </a>
              <a
                href={SOCIAL_LINKS.linkedin}
                target="_blank"
                rel="noopener noreferrer"
                className="text-white hover:text-white/80 transition-colors"
                aria-label="LinkedIn"
              >
                <FiLinkedin className="w-4 h-4" />
              </a>
              <a
                href={SOCIAL_LINKS.instagram}
                target="_blank"
                rel="noopener noreferrer"
                className="text-white hover:text-white/80 transition-colors"
                aria-label="Instagram"
              >
                <FiInstagram className="w-4 h-4" />
              </a>
              <div className="w-px h-4 bg-white/20" />
              <ArrowRight className="w-4 h-4 text-white/80 cursor-pointer hover:scale-105 transition-transform" />
            </div>

            <button
              className="liquid-glass rounded-full p-2 hover:scale-105 transition-transform cursor-pointer"
              aria-label="Account"
            >
              <Sparkles className="w-5 h-5 text-white" />
            </button>
          </div>

          {/* Community Card */}
          <div className="mt-6">
            <div className="liquid-glass rounded-2xl p-5 w-56">
              <h3 className="text-base font-medium text-white mb-2">
                Enter our ecosystem
              </h3>
              <p className="text-sm text-white/60">
                Join a community of creative minds shaping the future of floral design
              </p>
            </div>
          </div>

          {/* Bottom Feature Section */}
          <div className="mt-auto flex flex-col gap-4">
            {/* Outer Container */}
            <div className="liquid-glass rounded-[2rem] p-6">
              {/* Two Side-by-Side Cards */}
              <div className="flex gap-4 mb-4">
                {/* Processing Card */}
                <div className="liquid-glass rounded-3xl p-5 flex-1 flex flex-col items-center text-center hover:scale-105 transition-transform cursor-pointer">
                  <div className="w-10 h-10 rounded-full bg-white/10 flex items-center justify-center mb-3">
                    <Wand2 className="w-5 h-5 text-white" />
                  </div>
                  <p className="text-sm text-white/80">Processing</p>
                </div>

                {/* Growth Archive Card */}
                <div className="liquid-glass rounded-3xl p-5 flex-1 flex flex-col items-center text-center hover:scale-105 transition-transform cursor-pointer">
                  <div className="w-10 h-10 rounded-full bg-white/10 flex items-center justify-center mb-3">
                    <BookOpen className="w-5 h-5 text-white" />
                  </div>
                  <p className="text-sm text-white/80">Growth Archive</p>
                </div>
              </div>

              {/* Bottom Feature Card with Image */}
              <div className="liquid-glass rounded-3xl p-5 flex items-center gap-4 hover:scale-105 transition-transform cursor-pointer">
                <img
                  src="@/assets/hero-flowers.png"
                  alt="Flowers"
                  className="w-24 h-16 rounded-xl object-cover bg-white/10"
                />
                <div className="flex-1">
                  <h4 className="text-base font-medium text-white mb-1">
                    Advanced Plant Sculpting
                  </h4>
                  <p className="text-sm text-white/60">
                    Transform botanical ideas into stunning 3D visualizations
                  </p>
                </div>
                <button
                  className="w-8 h-8 rounded-full bg-white/10 flex items-center justify-center hover:scale-105 transition-transform"
                  aria-label="Add"
                >
                  <Plus className="w-4 h-4 text-white" />
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default BloomLanding;
