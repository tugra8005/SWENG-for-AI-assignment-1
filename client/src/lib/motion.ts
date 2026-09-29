import { useEffect, useState } from 'react';
import { AccessibilityInfo, Animated, Platform } from 'react-native';

/** Web'de ilk çizimden önce eşzamanlı okunur; yoksa animasyon bir kare başlayıp sonra durur. */
function initialReduced(): boolean {
  if (Platform.OS !== 'web' || typeof window === 'undefined' || !window.matchMedia) return false;
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/** ``prefers-reduced-motion`` (web) / sistem ayarı (Android). Açıksa animasyonlar kapanır. */
export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(initialReduced);
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
