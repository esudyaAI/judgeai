import {motion, useIsPresent, useReducedMotion, type HTMLMotionProps} from 'motion/react';
import {surfaceSpring} from './UiState';
/** Exit visuals never retain focusable or clickable controls. */
export function PresenceSurface(props: HTMLMotionProps<'div'>) {
  const present = useIsPresent();
  const reduce = useReducedMotion();
  return <motion.div {...props} inert={!present} aria-hidden={!present || undefined}
    initial={reduce ? false : {opacity:0,y:6,scale:0.985}} animate={{opacity:1,y:0,scale:1}}
    exit={{opacity:0,y:reduce ? 0 : 3,transition:{duration:reduce ? 0 : 0.1}}}
    transition={surfaceSpring} style={{...props.style,pointerEvents:present ? undefined : 'none'}} />;
}
