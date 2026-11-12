import unittest
from aicore.openapi import spec


class OpenAPITests(unittest.TestCase):
    def test_spec_has_auth_and_typed_requests(self):
        s = spec()
        self.assertEqual(s["openapi"], "3.1.0")
        self.assertIn("bearerAuth", s["components"]["securitySchemes"])
        self.assertEqual(s["paths"]["/healthz"]["get"]["security"], [])
        request = s["paths"]["/v1/tools/web_search"]["post"]["requestBody"]
        self.assertTrue(request["required"])
        self.assertEqual(request["content"]["application/json"]["schema"]["$ref"],
                         "#/components/schemas/SearchRequest")
        self.assertIn("/v1/models/reference", s["paths"])


if __name__ == "__main__":
    unittest.main()
