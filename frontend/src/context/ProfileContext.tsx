import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { createUser } from "../api/users";
import type { User, UserInput } from "../types";

const STORAGE_KEY = "englishtalker.profile.v1";

interface ProfileContextValue {
  profile: User | null;
  /** False until we've finished reading any saved profile from storage. */
  ready: boolean;
  /** Create (or replace) the profile on the backend and persist it locally. */
  saveProfile: (input: UserInput) => Promise<User>;
  /** Forget the local profile and return to onboarding. */
  signOut: () => Promise<void>;
}

const ProfileContext = createContext<ProfileContextValue | undefined>(undefined);

export function ProfileProvider({ children }: { children: ReactNode }) {
  const [profile, setProfile] = useState<User | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const stored = await AsyncStorage.getItem(STORAGE_KEY);
        if (stored) setProfile(JSON.parse(stored) as User);
      } finally {
        setReady(true);
      }
    })();
  }, []);

  const saveProfile = useCallback(async (input: UserInput) => {
    const user = await createUser(input);
    await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(user));
    setProfile(user);
    return user;
  }, []);

  const signOut = useCallback(async () => {
    await AsyncStorage.removeItem(STORAGE_KEY);
    setProfile(null);
  }, []);

  const value = useMemo(
    () => ({ profile, ready, saveProfile, signOut }),
    [profile, ready, saveProfile, signOut],
  );

  return <ProfileContext.Provider value={value}>{children}</ProfileContext.Provider>;
}

export function useProfile(): ProfileContextValue {
  const ctx = useContext(ProfileContext);
  if (!ctx) throw new Error("useProfile must be used within a ProfileProvider");
  return ctx;
}
