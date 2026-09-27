import { useEffect, useState } from 'react';
import { AccessibilityInfo, Animated } from 'react-native';

/** ``prefers-reduced-motion`` (web) / sistem ayarı (Android). Açıksa animasyonlar kapanır. */
export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    let alive = true;
    AccessibilityInfo.isReduceMotionEnabled().then((v) => alive && setReduced(v));
    const sub = AccessibilityInfo.addEventListener('reduceMotionChanged', setReduced);
    return () => {
      alive = false;
      sub.remove();
    };
  }, []);
  return reduced;
}

/**
 * ``Animated.Value`` için kararlı referans. React Native'in ``useAnimatedValue`` kancası
 * react-native-web'de yok; bu sürüm her iki platformda çalışır.
 */
export function useAnimatedValue(initial: number): Animated.Value {
  const [value] = useState(() => new Animated.Value(initial));
  return value;
}
