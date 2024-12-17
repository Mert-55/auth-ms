from fastapi import status

from .api_exception import APIException


class UserNotFoundError(APIException):
    status_code = status.HTTP_404_NOT_FOUND
    detail = "User not found"
    description = "This user does not exist."


class UserAlreadyExistsError(APIException):
    status_code = status.HTTP_409_CONFLICT
    detail = "User already exists"
    description = "This user name is already in use."


class EmailAlreadyExistsError(APIException):
    status_code = status.HTTP_409_CONFLICT
    detail = "Email already exists"
    description = "This email is already in use."


class InvalidEmailError(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    detail = "Invalid email"
    description = "This email is invalid."


class EmailNotVerifiedError(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    detail = "Email not verified"
    description = "The email has not been verified."


class EmailAlreadyVerifiedError(APIException):
    status_code = status.HTTP_412_PRECONDITION_FAILED
    detail = "Email already verified"
    description = "The email has already been verified."


class InvalidVerificationCodeError(APIException):
    status_code = status.HTTP_401_UNAUTHORIZED
    detail = "Invalid verification code"
    description = "The verification code is invalid."


class PasswordResetFailedError(APIException):
    status_code = status.HTTP_401_UNAUTHORIZED
    detail = "Password reset failed"
    description = (
        "The email or password reset code is invalid or the reset code has expired."
    )


class NoLoginMethodError(APIException):
    status_code = status.HTTP_412_PRECONDITION_FAILED
    detail = "No login method"
    description = "No login method was provided."


class RegistrationDisabledError(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    detail = "Registration disabled"
    description = "Registration is disabled."
