import { useEffect, useState } from 'react';
import { observeIndustryAccess, type IndustryAccess, type IndustryHost } from './industryAccess';

export function useIndustryAccess(host: IndustryHost | undefined, standalone: boolean) {
  const [access, setAccess] = useState<IndustryAccess>();
  useEffect(() => observeIndustryAccess(host, standalone, setAccess), [host, standalone]);
  return access;
}
