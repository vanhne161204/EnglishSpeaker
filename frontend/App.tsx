import { StatusBar } from "expo-status-bar";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { ProfileProvider } from "./src/context/ProfileContext";
import { RootNavigator } from "./src/navigation/RootNavigator";

export default function App() {
  return (
    <SafeAreaProvider>
      <StatusBar style="light" />
      <ProfileProvider>
        <RootNavigator />
      </ProfileProvider>
    </SafeAreaProvider>
  );
}
