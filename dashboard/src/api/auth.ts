import { http } from './http'
import type { ApiResponse, TokenData, User } from '@/types/api'

export const authApi = {
  async login(username: string, password: string): Promise<TokenData> {
    const response = await http.post<ApiResponse<TokenData>>('/auth/login', {
      username,
      password,
    })
    return response.data.data
  },

  async me(): Promise<User> {
    const response = await http.get<ApiResponse<User>>('/auth/me')
    return response.data.data
  },

  async logout(): Promise<void> {
    await http.post<ApiResponse<Record<string, never>>>('/auth/logout')
  },

  async changePassword(
    currentPassword: string,
    newPassword: string,
    confirmPassword: string,
  ): Promise<TokenData> {
    const response = await http.post<ApiResponse<TokenData>>('/auth/change-password', {
      current_password: currentPassword,
      new_password: newPassword,
      confirm_password: confirmPassword,
    })
    return response.data.data
  },
}
