
from locust import HttpUser, task, between, events
import random
import os
import sys

# Ensure scripts dir is in path to import utils
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from perf_utils import generate_csv_content

class PrimusUser(HttpUser):
    wait_time = between(1, 3)
    
    def on_start(self):
        """
        Login at the start of the session to get the token.
        Assumes we have a test admin user or uses the default one.
        """
        # Disable SSL warning
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        self.client.verify = False

        # Default credentials from docker-compose or .env
        self.username = os.environ.get("ADMIN_LOGIN", "SUPER_ADMIN")
        self.password = os.environ.get("ADMIN_PASSWORD", "Asdf#1234")
        
        response = self.client.post("/api/v1/auth/login", data={
            "username": self.username,
            "password": self.password
        })
        
        if response.status_code == 200:
            self.token = response.json()["access_token"]
            self.headers = {"Authorization": f"Bearer {self.token}"}
        else:
            print(f"Login failed: {response.text}")
            self.token = None
            self.headers = {}

    @task(1)
    def upload_csv_50(self):
        """Test Case: Import 50 items from CSV"""
        csv_content = generate_csv_content(50)
        files = {'file': ('import_50.csv', csv_content, 'text/csv')}
        
        with self.client.post(
            "/api/v1/product_definitions/import_csv", 
            files=files, 
            headers=self.headers, 
            catch_response=True,
            name="Import CSV (50 items)"
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"CSV 50 failed: {response.text}")

    @task(1)
    def upload_csv_5000(self):
        """Test Case: Import 5000 items from CSV (Heavy)"""
        csv_content = generate_csv_content(5000)
        files = {'file': ('import_5000.csv', csv_content, 'text/csv')}
        
        with self.client.post(
            "/api/v1/product_definitions/import_csv", 
            files=files, 
            headers=self.headers, 
            catch_response=True,
            name="Import CSV (5000 items)"
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"CSV 5000 failed: {response.text}")

    @task(5)
    def search_product(self):
        """Test Case: Search stock by product name filter"""
        # Testing the stock search endpoint which supports name filtering
        query = "Produkt" 
        with self.client.get(
            f"/api/v1/stock/?page=1&limit=10&name={query}", 
            headers=self.headers,
            catch_response=True,
            name="Search Stock"
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Search failed: {response.text}")

    @task(1)
    def generate_report(self):
        """Test Case: Generate Audit PDF"""
        with self.client.post(
            "/api/v1/reports/generate/audit", 
            headers=self.headers,
            catch_response=True,
            name="Generate Audit PDF"
        ) as response:
            # 202 Accepted is the correct success code for async generation
            if response.status_code == 202:
                response.success()
            else:
                response.failure(f"Report failed: {response.status_code} {response.text}")

    @task(3)
    def allocate_item(self):
        """Test Case: Full Inbound Allocation Flow (Find + Confirm)"""
        # Strategy: Search stock to get a valid product/barcode
        search_res = self.client.get("/api/v1/stock/?limit=5", headers=self.headers)
        if search_res.status_code == 200:
            groups = search_res.json()
            if groups and len(groups) > 0:
                group = random.choice(groups)
                if "product" in group and "barcode" in group["product"]:
                    barcode = group["product"]["barcode"]
                
                    # 1. Request Allocation
                    with self.client.post(
                        "/api/v1/stock/inbound/",
                        json={"barcode": barcode},
                        headers=self.headers,
                        catch_response=True,
                        name="Allocate (Step 1: Find Space)"
                    ) as response:
                        if response.status_code == 202: # 202 is success for finding space
                             allocation = response.json()
                             response.success()
                             
                             # 2. Confirm Allocation (Simulate putting item on shelf)
                             # Requires: designation, row, col from response
                             if "rack_designation" in allocation:
                                 confirm_payload = {
                                     "designation": allocation["rack_designation"],
                                     "row": allocation["row"],
                                     "col": allocation["col"]
                                 }
                                 with self.client.post(
                                     "/api/v1/stock/inbound/confirm",
                                     json=confirm_payload,
                                     headers=self.headers,
                                     catch_response=True,
                                     name="Allocate (Step 2: Confirm)"
                                 ) as confirm_res:
                                      if confirm_res.status_code == 201:
                                          confirm_res.success()
                                      else:
                                          confirm_res.failure(f"Confirm alloc failed: {confirm_res.status_code}")
                                          
                        elif response.status_code == 400: # Full is a valid business state
                             response.success()
                        else:
                            response.failure(f"Allocation failed: {response.status_code}")

    @task(3)
    def stock_outbound(self):
        """Test Case: Full Outbound Flow (Initiate + Confirm)"""
        search_res = self.client.get("/api/v1/stock/?limit=5", headers=self.headers)
        if search_res.status_code == 200:
            groups = search_res.json()
            if groups and len(groups) > 0:
                group = random.choice(groups)
                if "product" in group and "barcode" in group["product"]:
                    barcode = group["product"]["barcode"]
                
                    with self.client.post(
                        f"/api/v1/stock/outbound/initiate/{barcode}",
                        headers=self.headers,
                        catch_response=True,
                        name="Outbound (Step 1: Find Item)"
                    ) as response:
                        if response.status_code == 200:
                            location = response.json()
                            response.success()
                            
                            # 2. Confirm Outbound (Simulate taking item)
                            confirm_payload = {
                                "designation": location["designation"],
                                "row": location["row"],
                                "col": location["col"]
                            }
                            
                            with self.client.post(
                                "/api/v1/stock/outbound/confirm",
                                json=confirm_payload, # RackLocation schema
                                headers=self.headers,
                                catch_response=True,
                                name="Outbound (Step 2: Confirm)"
                            ) as confirm_res:
                                if confirm_res.status_code == 200:
                                    confirm_res.success()
                                else:
                                    confirm_res.failure(f"Confirm outbound failed: {confirm_res.status_code}")
                                    
                        elif response.status_code == 404: 
                            # Item not found/Out of stock - valid
                            response.success()
                        else:
                            response.failure(f"Outbound failed: {response.status_code}")

    @task(2)
    def ai_identify(self):
        """Test Case: AI Image Recognition"""
        # Uploads a small dummy image to checking processing overhead (task queuing)
        from perf_utils import generate_dummy_image
        image_data = generate_dummy_image()
        
        files = {'file': ('test_image.jpg', image_data, 'image/jpeg')}
        
        with self.client.post(
            "/api/v1/ai/recognize",
            files=files,
            headers=self.headers,
            catch_response=True,
            name="AI Identify (Task Queue)"
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"AI recognize failed: {response.text}")

    @task(2)
    def voice_command(self):
        """Test Case: Voice Command Processing"""
        # Sends a text to be processed by LLM
        payload = {"text": "dodaj produkt na półkę"}
        
        with self.client.post(
            "/api/v1/voice-command/",
            json=payload,
            headers=self.headers,
            catch_response=True,
            name="Voice Command (LLM)"
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Voice command failed: {response.status_code}")

