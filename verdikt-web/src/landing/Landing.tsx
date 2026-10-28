import { useRef } from 'react';
import { useScrollReveal } from '../hooks/motion';
import { Demo } from './Demo';
import { Hero, CaseWorkflow } from './Hero';
import { Nav } from './Nav';
import { Audience, Cta, Faq, Features, Footer, HowItWorks, LawHighlight } from './Sections';
import './landing.css';

export function Landing() {
  const root = useRef<HTMLDivElement>(null);
  useScrollReveal(root);
  return (
    <div ref={root} className="landing">
      <Nav />
      <main>
        <Hero />
        <CaseWorkflow />
        <Demo />
        <Audience />
        <HowItWorks />
        <Features />
        <LawHighlight />
        <Faq />
        <Cta />
      </main>
      <Footer />
    </div>
  );
}
