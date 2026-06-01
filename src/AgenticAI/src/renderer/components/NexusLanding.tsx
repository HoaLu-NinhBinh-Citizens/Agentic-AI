import React from 'react';
import {
  Sparkles,
  Rocket,
  Puzzle,
  Users,
  Menu,
  ArrowRight,
  User,
  Plus,
  Brain,
  Network,
} from 'lucide-react';
import { FiGithub, FiMessageCircle, FiTwitter } from 'react-icons/fi';

interface NexusLandingProps {
  onLaunchStudio?: () => void;
}

const VIDEO_URL = 'https://cdn.coverr.co/videos/coverr-artificial-intelligence-concept-8762/1080p.mp4';

const SOCIAL_LINKS = {
  github: 'https://github.com/nexus',
  discord: 'https://discord.gg/nexus',
  twitter: 'https://twitter.com/nexus',
};

export const NexusLanding: React.FC<NexusLandingProps> = ({ onLaunchStudio }) => {
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
        <div className="w-full lg:w-[52%] h-screen flex flex-col p-4 lg:p-6 relative">
          {/* Liquid Glass Strong Overlay */}
          <div className="absolute inset-4 lg:inset-6 rounded-[1.5rem] liquid-glass-strong pointer-events-none" />

          {/* Navigation */}
          <nav className="relative z-20 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Network className="w-8 h-8 text-white" strokeWidth={1.5} />
              <span className="text-2xl font-semibold tracking-tight text-white">
                nexus
              </span>
            </div>
            <button
              className="liquid-glass rounded-full px-4 py-2 flex items-center gap-2 text-white text-sm hover:scale-105 transition-all duration-300 cursor-pointer"
              aria-label="Open menu"
            >
              <Menu className="w-4 h-4" />
              <span>Menu</span>
            </button>
          </nav>

          {/* Hero Center Content */}
          <div className="flex-1 flex flex-col items-center justify-center relative z-20">
            {/* Hero Logo */}
            <Network className="w-20 h-20 text-white mb-8" strokeWidth={1.5} />

            {/* Hero Headline */}
            <h1 className="text-5xl md:text-6xl lg:text-7xl font-medium tracking-[-0.05em] text-white text-center mb-10 leading-tight">
              Orchestrate the{' '}
              <span className="block font-serif italic text-white/80">
                intelligence of agents
              </span>
            </h1>

            {/* CTA Button */}
            <button 
              onClick={onLaunchStudio}
              className="liquid-glass-strong rounded-full px-8 py-4 flex items-center gap-3 text-white mb-10 hover:scale-105 active:scale-95 transition-all duration-300 cursor-pointer"
            >
              <span className="text-base font-medium">Launch Studio</span>
              <div className="w-7 h-7 rounded-full bg-white/15 flex items-center justify-center">
                <Sparkles className="w-4 h-4" />
              </div>
            </button>

            {/* Feature Pills */}
            <div className="flex flex-wrap justify-center gap-3">
              <span className="liquid-glass rounded-full px-4 py-2 text-xs text-white/80 hover:scale-105 transition-all duration-300 cursor-pointer">
                Multi-Agent Workflows
              </span>
              <span className="liquid-glass rounded-full px-4 py-2 text-xs text-white/80 hover:scale-105 transition-all duration-300 cursor-pointer">
                Auto-GPT Core
              </span>
              <span className="liquid-glass rounded-full px-4 py-2 text-xs text-white/80 hover:scale-105 transition-all duration-300 cursor-pointer">
                Observability
              </span>
            </div>
          </div>

          {/* Bottom Quote */}
          <div className="relative z-20 text-center mt-auto">
            <p className="text-xs tracking-widest uppercase text-white/50 mb-3">
              AGENTIC PARADIGM
            </p>
            <blockquote className="text-lg md:text-xl text-white mb-4 font-display">
              &ldquo;AI that plans, acts, and learns without handholding.&rdquo;
            </blockquote>
            <div className="flex items-center justify-center gap-4">
              <div className="h-px w-12 bg-white/30" />
              <p className="text-sm font-medium tracking-wider text-white/60">
                ALEXANDRA CORTEZ
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
                href={SOCIAL_LINKS.github}
                target="_blank"
                rel="noopener noreferrer"
                className="text-white hover:text-white/80 transition-all duration-300"
                aria-label="GitHub"
              >
                <FiGithub className="w-4 h-4" />
              </a>
              <a
                href={SOCIAL_LINKS.discord}
                target="_blank"
                rel="noopener noreferrer"
                className="text-white hover:text-white/80 transition-all duration-300"
                aria-label="Discord"
              >
                <Users className="w-4 h-4" />
              </a>
              <a
                href={SOCIAL_LINKS.twitter}
                target="_blank"
                rel="noopener noreferrer"
                className="text-white hover:text-white/80 transition-all duration-300"
                aria-label="Twitter"
              >
                <ArrowRight className="w-4 h-4 rotate-[-45deg]" />
              </a>
              <div className="w-px h-4 bg-white/20" />
              <ArrowRight className="w-4 h-4 text-white/80 cursor-pointer hover:scale-105 transition-all duration-300" />
            </div>

            <button
              className="liquid-glass rounded-full p-2 hover:scale-105 transition-all duration-300 cursor-pointer"
              aria-label="Account"
            >
              <User className="w-5 h-5 text-white" />
            </button>
          </div>

          {/* Community Card */}
          <div className="mt-6">
            <div className="liquid-glass rounded-2xl p-5 w-56">
              <h3 className="text-base font-medium text-white mb-2">
                Join the Agentic Network
              </h3>
              <p className="text-sm text-white/60">
                Early access to swarm intelligence.
              </p>
            </div>
          </div>

          {/* Bottom Feature Section */}
          <div className="mt-auto flex flex-col gap-4">
            {/* Outer Container */}
            <div className="liquid-glass rounded-[2rem] p-6">
              {/* Two Side-by-Side Cards */}
              <div className="flex gap-4 mb-4">
                {/* Agent Builder Card */}
                <div className="liquid-glass rounded-3xl p-5 flex-1 flex flex-col items-center text-center hover:scale-105 transition-all duration-300 cursor-pointer">
                  <div className="w-8 h-8 rounded-full bg-white/10 flex items-center justify-center mb-3">
                    <Puzzle className="w-5 h-5 text-white" />
                  </div>
                  <p className="text-sm text-white/80">Agent Builder</p>
                </div>

                {/* Deployments Card */}
                <div className="liquid-glass rounded-3xl p-5 flex-1 flex flex-col items-center text-center hover:scale-105 transition-all duration-300 cursor-pointer">
                  <div className="w-8 h-8 rounded-full bg-white/10 flex items-center justify-center mb-3">
                    <Rocket className="w-5 h-5 text-white" />
                  </div>
                  <p className="text-sm text-white/80">Deployments</p>
                </div>
              </div>

              {/* Bottom Feature Card with Image */}
              <div className="liquid-glass rounded-3xl p-5 flex items-center gap-4 hover:scale-105 transition-all duration-300 cursor-pointer">
                <div className="w-24 h-16 rounded-xl bg-gradient-to-br from-white/20 to-white/5" />
                <div className="flex-1">
                  <h4 className="text-base font-medium text-white mb-1">
                    Live Agent Topology
                  </h4>
                  <p className="text-sm text-white/60">
                    Visualize and manage your agent network
                  </p>
                </div>
                <button
                  className="w-8 h-8 rounded-full bg-white/10 flex items-center justify-center hover:scale-105 transition-all duration-300"
                  aria-label="Add new agent"
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

export default NexusLanding;
