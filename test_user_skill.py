
from justllama.server.skills.base import AgentSkill
class MySkill(AgentSkill):
    def get_name(self): return "my_skill"
    def get_description(self): return "My custom skill"
    def get_tool_schema(self): return {}
    def execute(self, args, cancel_check=None): return "hello"
