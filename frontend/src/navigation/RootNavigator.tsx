import { NavigationContainer } from "@react-navigation/native";
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import { ActivityIndicator, Text, View } from "react-native";
import { RoomsStack } from "./RoomsStack";
import { NotesScreen } from "../screens/NotesScreen";
import { OnboardingScreen } from "../screens/OnboardingScreen";
import { ProfileScreen } from "../screens/ProfileScreen";
import { useProfile } from "../context/ProfileContext";
import { theme } from "../theme";

// Rooms covers both group rooms and 1-on-1s — they are one model, filtered by kind.
export type RootTabParamList = {
  Rooms: undefined;
  Notes: undefined;
  Profile: undefined;
};

const Tab = createBottomTabNavigator<RootTabParamList>();

const ICONS: Record<keyof RootTabParamList, string> = {
  Rooms: "🚪",
  Notes: "📝",
  Profile: "👤",
};

const headerOptions = {
  headerShown: true,
  headerStyle: { backgroundColor: theme.colors.primary },
  headerTintColor: "#FFFFFF",
  headerTitleStyle: { fontWeight: "700" as const },
};

function MainTabs() {
  return (
    <Tab.Navigator
      screenOptions={({ route }) => ({
        headerShown: false,
        tabBarActiveTintColor: theme.colors.primary,
        tabBarInactiveTintColor: theme.colors.muted,
        tabBarIcon: ({ focused }) => (
          <Text style={{ fontSize: 18, opacity: focused ? 1 : 0.6 }}>{ICONS[route.name]}</Text>
        ),
      })}
    >
      <Tab.Screen name="Rooms" component={RoomsStack} />
      <Tab.Screen name="Notes" component={NotesScreen} options={headerOptions} />
      <Tab.Screen name="Profile" component={ProfileScreen} options={headerOptions} />
    </Tab.Navigator>
  );
}

export function RootNavigator() {
  const { profile, ready } = useProfile();

  return (
    <NavigationContainer>
      {!ready ? (
        <View style={{ flex: 1, justifyContent: "center", backgroundColor: theme.colors.background }}>
          <ActivityIndicator color={theme.colors.primary} />
        </View>
      ) : profile ? (
        <MainTabs />
      ) : (
        <OnboardingScreen />
      )}
    </NavigationContainer>
  );
}
