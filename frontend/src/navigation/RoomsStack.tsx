import { createNativeStackNavigator } from "@react-navigation/native-stack";
import { RoomsScreen } from "../screens/RoomsScreen";
import { RoomDetailScreen } from "../screens/RoomDetailScreen";
import { RoomChatScreen } from "../screens/RoomChatScreen";
import { theme } from "../theme";
import type { Room } from "../types";

export type RoomsStackParamList = {
  RoomsList: undefined;
  RoomDetail: { room: Room };
  RoomChat: { room: Room };
};

const Stack = createNativeStackNavigator<RoomsStackParamList>();

export function RoomsStack() {
  return (
    <Stack.Navigator
      screenOptions={{
        headerStyle: { backgroundColor: theme.colors.primary },
        headerTintColor: "#FFFFFF",
        headerTitleStyle: { fontWeight: "700" },
      }}
    >
      <Stack.Screen name="RoomsList" component={RoomsScreen} options={{ title: "Rooms" }} />
      <Stack.Screen
        name="RoomDetail"
        component={RoomDetailScreen}
        options={{ title: "Room", headerBackTitle: "Rooms" }}
      />
      <Stack.Screen
        name="RoomChat"
        component={RoomChatScreen}
        options={{ title: "Text chat", headerBackTitle: "Room" }}
      />
    </Stack.Navigator>
  );
}
